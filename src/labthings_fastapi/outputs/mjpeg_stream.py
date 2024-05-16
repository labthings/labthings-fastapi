from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, HTMLResponse
from typing import (
    AsyncGenerator,
    AsyncIterator,
    Literal,
    Optional,
    TYPE_CHECKING,
    Union,
    overload,
)
from typing_extensions import Self
from copy import copy
from contextlib import asynccontextmanager
import threading
import anyio
from anyio.from_thread import BlockingPortal
import logging

if TYPE_CHECKING:
    from ..thing import Thing


@dataclass
class RingbufferEntry:
    """A single entry in a ringbuffer"""

    frame: bytes
    timestamp: datetime
    index: int


class MJPEGStreamResponse(StreamingResponse):
    media_type = "multipart/x-mixed-replace; boundary=frame"

    def __init__(self, gen: AsyncGenerator[bytes, None], status_code: int = 200):
        """A StreamingResponse that streams an MJPEG stream

        This response is initialised with an async generator that yields `bytes`
        objects, each of which is a JPEG file. We add the --frame markers and mime
        types that enable it to work in an `img` tag.

        NB the ``status_code`` argument is used by FastAPI to set the status code of
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
        self._ringbuffer: list[RingbufferEntry] = []
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
        """Return the ith frame acquired by the camera

        :param i: The index of the frame to read
        """
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
    async def buffer_for_reading(self, i: int) -> AsyncIterator[bytes]:
        """Yields the ith frame as a bytes object

        :param i: The index of the frame to read
        """
        entry = await self.ringbuffer_entry(i)
        yield entry.frame

    async def next_frame(self) -> int:
        """Wait for the next frame, and return its index"""
        async with self.condition:
            await self.condition.wait()
            return self.last_frame_i

    async def grab_frame(self) -> bytes:
        """Wait for the next frame, and return it

        This copies the frame for safety, so we can release the
        read lock on the buffer.
        """
        i = await self.next_frame()
        async with self.buffer_for_reading(i) as frame:
            return copy(frame)

    async def next_frame_size(self) -> int:
        """Wait for the next frame and return its size

        This is useful if you want to use JPEG size as a sharpness metric.
        """
        i = await self.next_frame()
        async with self.buffer_for_reading(i) as frame:
            return len(frame)

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
        """Return the next buffer in the ringbuffer to write to

        :param frame: The frame to add
        :param portal: The blocking portal to use for scheduling tasks.
            This is necessary because tasks are handled asynchronously.
            The blocking portal may be obtained with a dependency, in
            `labthings_fastapi.dependencies.blocking_portal.BlockingPortal`.
        """
        assert frame[0] == 0xFF and frame[1] == 0xD8, ValueError("Invalid JPEG")
        assert frame[-2] == 0xFF and frame[-1] == 0xD9, ValueError("Invalid JPEG")
        with self._lock:
            entry = self._ringbuffer[(self.last_frame_i + 1) % len(self._ringbuffer)]
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

    @overload
    def __get__(self, obj: Literal[None], type=None) -> Self: ...

    @overload
    def __get__(self, obj: Thing, type=None) -> MJPEGStream: ...

    def __get__(self, obj: Optional[Thing], type=None) -> Union[MJPEGStream, Self]:
        """The value of the property

        If ``obj`` is none (i.e. we are getting the attribute of the class),
        we return the descriptor.

        If no getter is set, we'll return either the initial value, or the value
        from the object's ``__dict__``, i.e. we behave like a variable.

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

        @app.get(
            f"{thing.path}{self.name}/viewer",
            response_class=HTMLResponse,
        )
        async def viewer_page():
            return await self.viewer_page(f"{thing.path}{self.name}")
