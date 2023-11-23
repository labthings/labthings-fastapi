import logging
import threading

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from labthings_fastapi.descriptors.property import PropertyDescriptor
from labthings_fastapi.thing import Thing
from labthings_fastapi.decorators import thing_action, thing_property
from labthings_fastapi.thing_server import ThingServer
from labthings_fastapi.file_manager import FileManagerDep
from typing import Optional, AsyncContextManager
from collections.abc import AsyncGenerator
from functools import partial
from dataclasses import dataclass
from datetime import datetime
from contextlib import asynccontextmanager
import anyio
from anyio.from_thread import BlockingPortal
from threading import RLock
import cv2 as cv

logging.basicConfig(level=logging.INFO)


@dataclass
class RingbufferEntry:
    """A single entry in a ringbuffer"""

    frame: bytes
    timestamp: datetime
    index: int
    readers: int = 0


class MJPEGStreamResponse(StreamingResponse):
    media_type = "multipart/x-mixed-replace; boundary=frame"

    def __init__(self, gen: AsyncGenerator[bytes, None], status_code: int = 200):
        """A StreamingResponse that streams an MJPEG stream

        This response is initialised with an async generator that yields `bytes`
        objects, each of which is a JPEG file. We add the --frame markers and mime
        types that enable it to work in an `img` tag.

        NB the `status_code` argument is used by FastAPI to set the status code of
        the response in OpenAPI.
        """
        self.frame_async_generator = gen
        StreamingResponse.__init__(
            self,
            self.mjpeg_async_generator(),
            media_type=self.media_type,
            status_code=status_code,
        )

    async def mjpeg_async_generator(self) -> AsyncGenerator[bytes, None]:
        """A generator yielding an MJPEG stream"""
        async for frame in self.frame_async_generator:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
            yield frame
            yield b"\r\n"


class MJPEGStream:
    def __init__(self, ringbuffer_size: int = 10):
        self._lock = threading.Lock()
        self.condition = anyio.Condition()
        self._streaming = False
        self.reset(ringbuffer_size=ringbuffer_size)

    def reset(self, ringbuffer_size: Optional[int] = None):
        """Reset the stream and optionally change the ringbuffer size"""
        with self._lock:
            self._streaming = True
            n = ringbuffer_size or len(self._ringbuffer)
            self._ringbuffer = [
                RingbufferEntry(
                    frame=b"",
                    index=-1,
                    timestamp=datetime.min,
                )
                for i in range(n)
            ]
            self.last_frame_i = -1

    def stop(self):
        """Stop the stream"""
        with self._lock:
            self._streaming = False

    async def ringbuffer_entry(self, i: int) -> RingbufferEntry:
        """Return the `i`th frame acquired by the camera"""
        if i < 0:
            raise ValueError("i must be >= 0")
        if i < self.last_frame_i - len(self._ringbuffer) + 2:
            raise ValueError("the ith frame has been overwritten")
        if i > self.last_frame_i:
            # TODO: await the ith frame
            raise ValueError("the ith frame has not yet been acquired")
        entry = self._ringbuffer[i % len(self._ringbuffer)]
        if entry.index != i:
            raise ValueError("the ith frame has been overwritten")
        return entry

    @asynccontextmanager
    async def buffer_for_reading(self, i: int) -> AsyncContextManager[bytes]:
        """Yields the ith frame as a bytes object"""
        entry = await self.ringbuffer_entry(i)
        try:
            entry.readers += 1
            yield entry.frame
        finally:
            entry.readers -= 1

    async def next_frame(self) -> int:
        """Wait for the next frame, and return its index"""
        async with self.condition:
            await self.condition.wait()
            return self.last_frame_i

    async def frame_async_generator(self) -> AsyncGenerator[bytes, None]:
        """A generator that yields frames as bytes"""
        while self._streaming:
            try:
                i = await self.next_frame()
                async with self.buffer_for_reading(i) as frame:
                    yield frame
            except Exception as e:
                logging.error(f"Error in stream: {e}, stream stopped")
                return

    async def mjpeg_stream_response(self) -> MJPEGStreamResponse:
        """Return a StreamingResponse that streams an MJPEG stream"""
        return MJPEGStreamResponse(self.frame_async_generator())

    def add_frame(self, frame: bytes, portal: BlockingPortal):
        """Return the next buffer in the ringbuffer to write to"""
        with self._lock:
            entry = self._ringbuffer[(self.last_frame_i + 1) % len(self._ringbuffer)]
            if entry.readers > 0:
                raise RuntimeError("Cannot write to ringbuffer while it is being read")
            entry.timestamp = datetime.now()
            entry.frame = frame
            entry.index = self.last_frame_i + 1
            portal.start_task_soon(self.notify_new_frame, entry.index)

    async def notify_new_frame(self, i):
        """Notify any waiting tasks that a new frame is available"""
        async with self.condition:
            self.last_frame_i = i
            self.condition.notify_all()


class MJPEGStreamDescriptor:
    """A descriptor that returns a MJPEGStream object when accessed"""

    def __init__(self, **kwargs):
        self._kwargs = kwargs

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, type=None) -> MJPEGStream:
        """The value of the property

        If `obj` is none (i.e. we are getting the attribute of the class),
        we return the descriptor.

        If no getter is set, we'll return either the initial value, or the value
        from the object's __dict__, i.e. we behave like a variable.

        If a getter is set, we will use it, unless the property is observable, at
        which point the getter is only ever used once, to set the initial value.
        """
        if obj is None:
            return self
        try:
            return obj.__dict__[self.name]
        except KeyError:
            obj.__dict__[self.name] = MJPEGStream(**self._kwargs)
            return obj.__dict__[self.name]

    async def viewer_page(self, url: str) -> HTMLResponse:
        return HTMLResponse(f"<html><body><img src='{url}'></body></html>")

    def add_to_fastapi(self, app: FastAPI, thing: Thing):
        """Add the stream to the FastAPI app"""
        app.get(
            f"{thing.path}{self.name}",
            response_class=MJPEGStreamResponse,
        )(self.__get__(thing).mjpeg_stream_response)
        app.get(
            f"{thing.path}{self.name}/viewer",
            response_class=HTMLResponse,
        )(partial(self.viewer_page, f"{thing.path}{self.name}"))


class OpenCVCamera(Thing):
    """A Thing that represents an OpenCV camera"""

    def __init__(self, device_index: int = 0):
        self.device_index = device_index
        self._stream_thread: Optional[threading.Thread] = None

    def __enter__(self):
        self._cap = cv.VideoCapture(self.device_index)
        self._cap_lock = RLock()
        if not self._cap.isOpened():
            raise IOError(f"Cannot open camera with device index {self.device_index}")
        self.start_streaming()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop_streaming()
        self._cap.release()
        del self._cap
        del self._cap_lock

    def start_streaming(self):
        print("starting stream...")
        if self._stream_thread is not None:
            raise RuntimeError("Stream thread already running")
        self._stream_thread = threading.Thread(target=self._stream_thread_fn)
        self._continue_streaming = True
        self._stream_thread.start()
        print("started")

    def stop_streaming(self):
        print("stopping stream...")
        if self._stream_thread is None:
            raise RuntimeError("Stream thread not running")
        self._continue_streaming = False
        self.mjpeg_stream.stop()
        print("waiting for stream to join")
        self._stream_thread.join()
        print("stream stopped.")
        self._stream_thread = None

    def _stream_thread_fn(self):
        while self._continue_streaming:
            with self._cap_lock:
                ret, frame = self._cap.read()
                if not ret:
                    logging.error("Could not read frame from camera")
                    continue
            success, array = cv.imencode(".jpg", frame)
            if success:
                self.mjpeg_stream.add_frame(
                    frame=array.tobytes(),
                    portal=self._labthings_blocking_portal,
                )
                self.last_frame_index = self.mjpeg_stream.last_frame_i

    @thing_action
    def snap_image(self, file_manager: FileManagerDep) -> str:
        """Acquire one image from the camera.

        This action cannot run if the camera is in use by a background thread, for
        example if a preview stream is running.
        """
        with self._cap_lock:
            ret, frame = self._cap.read()
            if not ret:
                raise IOError("Could not read image from camera")
            fpath = file_manager.path("image.jpg", rel="image")
            cv.imwrite(fpath, frame)
            return (
                "image.jpg is available from the links property of this Invocation "
                "(see ./files)"
            )

    @thing_property
    def exposure(self) -> float:
        with self._cap_lock:
            return self._cap.get(cv.CAP_PROP_EXPOSURE)

    @exposure.setter
    def exposure(self, value):
        with self._cap_lock:
            self._cap.set(cv.CAP_PROP_EXPOSURE, value)

    last_frame_index = PropertyDescriptor(int, initial_value=-1)

    mjpeg_stream = MJPEGStreamDescriptor(ringbuffer_size=10)


thing_server = ThingServer()
my_thing = OpenCVCamera()
my_thing.validate_thing_description()
thing_server.add_thing(my_thing, "/camera")

app = thing_server.app
