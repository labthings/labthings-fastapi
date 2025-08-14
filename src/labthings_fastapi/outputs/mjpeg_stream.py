"""MJPEG Stream support.

This module defines a descriptor that allows `.Thing` subclasses to expose an
MJPEG stream. See `.MJPEGStreamDescriptor`.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, HTMLResponse
from typing import (
    Any,
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
    """A single entry in a ringbuffer.

    This structure comprises one frame as a JPEG, plus a timestamp and
    a buffer index. Each time a frame is added to the stream, it is
    tagged with a timestamp and index, with the index increasing by
    1 each time.
    """

    frame: bytes
    """The frame as a `bytes` object, which is a JPEG image for an MJPEG stream."""
    timestamp: datetime
    """The time the frame was added to the ringbuffer."""
    index: int
    """The index of the frame within the stream."""


class MJPEGStreamResponse(StreamingResponse):
    """A StreamingResponse that streams an MJPEG stream.

    This response uses an async generator that yields `bytes`
    objects, each of which is a JPEG file. We add the --frame markers and mime
    types that mark it as an MJPEG stream. This is sufficient to enable it to
    work in an `img` tag, with the `src` set to the MJPEG stream's endpoint.
    """

    media_type = "multipart/x-mixed-replace; boundary=frame"
    """The media_type used to describe the endpoint in FastAPI."""

    def __init__(self, gen: AsyncGenerator[bytes, None], status_code: int = 200):
        """Set up StreamingResponse that streams an MJPEG stream.

        This response is initialised with an async generator that yields `bytes`
        objects, each of which is a JPEG file. We add the --frame markers and mime
        types that mark it as an MJPEG stream. This is sufficient to enable it to
        work in an `img` tag, with the `src` set to the MJPEG stream's endpoint.

        It expects an async generator that supplies individual JPEGs to be streamed,
        such as the one provided by `.MJPEGStream`.

        NB the ``status_code`` argument is used by FastAPI to set the status code of
        the response in OpenAPI.

        :param gen: an async generator, yielding `bytes` objects each of which is
            one image, in JPEG format.
        :param status_code: The status code associated with the response, by default
            a 200 code is returned.
        """
        self.frame_async_generator = gen
        StreamingResponse.__init__(
            self,
            self.mjpeg_async_generator(),
            media_type=self.media_type,
            status_code=status_code,
        )

    async def mjpeg_async_generator(self) -> AsyncGenerator[bytes, None]:
        """Return a generator yielding an MJPEG stream.

        This async generator wraps each incoming JPEG frame with the
        ``--frame`` separator and content type header. It is the basis
        of the response sent over HTTP (see ``__init__``).

        :yield: JPEG frames, each with a ``--frame`` marker prepended.
        """
        async for frame in self.frame_async_generator:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
            yield frame
            yield b"\r\n"


class MJPEGStream:
    """Manage streaming images over HTTP as an MJPEG stream.

    An MJPEGStream object handles accepting images (already in
    JPEG format) and streaming them to HTTP clients as a multipart
    response.

    The minimum needed to make the stream work is to periodically
    call `add_frame` with JPEG image data.

    To add a stream to a `.Thing`, use the `.MJPEGStreamDescriptor`
    which will handle creating an `.MJPEGStream` object on first access,
    and will also add it to the HTTP API.

    The MJPEG stream buffers the last few frames (10 by default) and
    also has a hook to notify the size of each frame as it is added.
    The latter is used by OpenFlexure's autofocus routine. The
    ringbuffer is intended to support clients receiving notification
    of new frames, and then retrieving the frame (shortly) afterwards.
    """

    def __init__(self, ringbuffer_size: int = 10):
        """Initialise an MJPEG stream.

        See the class docstring for `.MJPEGStream`. Note that it will
        often be initialised by `.MJPEGStreamDescriptor`.

        :param ringbuffer_size: The number of frames to retain in
            memory, to allow retrieval after the frame has been sent.
        """
        self._lock = threading.Lock()
        self.condition = anyio.Condition()
        self._streaming = False
        self._ringbuffer: list[RingbufferEntry] = []
        self.reset(ringbuffer_size=ringbuffer_size)

    def reset(self, ringbuffer_size: Optional[int] = None) -> None:
        """Reset the stream and optionally change the ringbuffer size.

        Discard all frames from the ringbuffer and reset the frame index.

        :param ringbuffer_size: the number of frames to keep in memory.
        """
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

    def stop(self, portal: BlockingPortal) -> None:
        """Stop the stream.

        Stop the stream and cause all clients to disconnect.

        :param portal: an `anyio.from_thread.BlockingPortal` that allows
            this function to use the event loop to notify that the stream
            should stop.
        """
        with self._lock:
            self._streaming = False
            portal.start_task_soon(self.notify_stream_stopped)

    async def ringbuffer_entry(self, i: int) -> RingbufferEntry:
        """Return the ith frame acquired by the camera.

        The ringbuffer means we can retrieve frames even if they are not
        the latest frame. Specifying ``i`` also makes it simple to ensure
        that every frame in a stream is acquired.

        :param i: The index of the frame to read.

        :return: the frame, together with a timestamp and its index.

        :raise ValueError: if the frame is not available.
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
        """Yield the ith frame as a bytes object.

        Retrieve frame ``i`` from the ringbuffer.

        This allows async code access to a frame in the ringbuffer.
        The frame will not be copied, and should not be written to.
        The frame may not exist after the function has completed (i.e.
        after any ``with`` statement has finished).

        Using a context manager is intended to allow future versions of this
        code to manage access to the ringbuffer (e.g. allowing buffer reuse).
        Currently, buffers are always created as fresh `bytes` objects, so
        this context manager does not provide additional functionality
        over `.MJPEGStream.ringbuffer_entry`.

        :param i: The index of the frame to read

        :yield: The frame's data as `bytes`, along with timestamp and index.
        """
        entry = await self.ringbuffer_entry(i)
        yield entry.frame

    async def next_frame(self) -> int:
        """Wait for the next frame, and return its index.

        This async function will yield until a new frame arrives, then return
        its index. The index may then be used to retrieve the new frame
        with `.MJPEGStream.buffer_for_reading`.

        :return: the index of the next frame to arrive.

        :raise StopAsyncIteration: if the stream has stopped.
        """
        async with self.condition:
            await self.condition.wait()
            if not self._streaming:
                raise StopAsyncIteration()
            return self.last_frame_i

    async def grab_frame(self) -> bytes:
        """Wait for the next frame, and return it.

        This copies the frame for safety, so there is no need to release
        or return the buffer.

        :return: The next JPEG frame, as a `bytes` object.
        """
        i = await self.next_frame()
        async with self.buffer_for_reading(i) as frame:
            return copy(frame)

    async def next_frame_size(self) -> int:
        """Wait for the next frame and return its size.

        This is useful if you want to use JPEG size as a sharpness metric.

        :return: The size of the next JPEG frame, in bytes.
        """
        i = await self.next_frame()
        async with self.buffer_for_reading(i) as frame:
            return len(frame)

    async def frame_async_generator(self) -> AsyncGenerator[bytes, None]:
        """Yield frames as bytes objects.

        This generator will return frames from the MJPEG stream. These are
        taken from the ringbuffer by `.MJPEGStream.buffer_for_reading` and
        so should have any buffer-management considerations taken care of.

        Code using this generator should complete as quickly as possible,
        because future implementations may hold a lock while this function
        yields. If lengthy processing is required, please copy the buffer
        and continue processing elsewhere.

        Note that this will wait for a new frame each time. There is no
        guarantee that we won't skip frames.

        :yield: the frames in sequence, as a `bytes` object containing
            JPEG data.
        """
        while self._streaming:
            try:
                i = await self.next_frame()
                async with self.buffer_for_reading(i) as frame:
                    yield frame
            except StopAsyncIteration:
                break
            except Exception as e:
                logging.error(f"Error in stream: {e}, stream stopped")
                return

    async def mjpeg_stream_response(self) -> MJPEGStreamResponse:
        """Return a StreamingResponse that streams an MJPEG stream.

        This wraps each frame with the required header to make the
        multipart stream work, and sends it to the client via a
        streaming response. It is sufficient to show up as a video
        in an ``img`` tag, or to be streamed to disk as an MJPEG
        format video.

        :return: a streaming response in MJPEG format.
        """
        return MJPEGStreamResponse(self.frame_async_generator())

    def add_frame(self, frame: bytes, portal: BlockingPortal) -> None:
        """Add a JPEG to the MJPEG stream.

        This function adds a frame to the stream. It may be called from
        threaded code, but uses an `anyio.from_thread.BlockingPortal` to
        call code in the `anyio` event loop, which is where notifications
        are handled.

        :param frame: The frame to add
        :param portal: The blocking portal to use for scheduling tasks.
            This is necessary because tasks are handled asynchronously.
            The blocking portal may be obtained with a dependency, in
            `labthings_fastapi.dependencies.blocking_portal.BlockingPortal`.

        :raise ValueError: if the supplied frame does not start with the JPEG
            start bytes and end with the end bytes.
        """
        if not (
            frame[0] == 0xFF
            and frame[1] == 0xD8
            and frame[-2] == 0xFF
            and frame[-1] == 0xD9
        ):
            raise ValueError("Invalid JPEG")
        with self._lock:
            entry = self._ringbuffer[(self.last_frame_i + 1) % len(self._ringbuffer)]
            entry.timestamp = datetime.now()
            entry.frame = frame
            entry.index = self.last_frame_i + 1
            portal.start_task_soon(self.notify_new_frame, entry.index)

    async def notify_new_frame(self, i: int) -> None:
        """Notify any waiting tasks that a new frame is available.

        :param i: The number of the frame (which counts up since the server starts)
        """
        async with self.condition:
            self.last_frame_i = i
            self.condition.notify_all()

    async def notify_stream_stopped(self) -> None:
        """Raise an exception in any waiting tasks to signal the stream has stopped."""
        assert self._streaming is False
        async with self.condition:
            self.condition.notify_all()


class MJPEGStreamDescriptor:
    """A descriptor that returns a MJPEGStream object when accessed.

    If this descriptor is added to a `.Thing`, it will create an `.MJPEGStream`
    object when it is first accessed. It will also add two HTTP endpoints,
    one with the name of the descriptor serving the MJPEG stream, and another
    with `/viewer` appended, which serves a basic HTML page that views the stream.

    This descriptor does not currently show up in the :ref:`wot_td`.
    """

    def __init__(self, **kwargs: Any):
        r"""Initialise an MJPEGStreamDescriptor.

        :param \**kwargs: keyword arguments are passed to the initialiser of
            `.MJPEGStream`.
        """
        self._kwargs: Any = kwargs

    def __set_name__(self, _owner: Thing, name: str) -> None:
        """Remember the name to which we are assigned.

        The name is important, as it will set the URL of the HTTP endpoint used
        to access the stream.

        :param _owner: the `.Thing` to which we are attached.
        :param name: the name to which this descriptor is assigned.
        """
        self.name = name

    @overload
    def __get__(self, obj: Literal[None], type: type | None = None) -> Self: ...  # noqa: D105

    @overload
    def __get__(self, obj: Thing, type: type | None = None) -> MJPEGStream: ...  # noqa: D105

    def __get__(
        self, obj: Optional[Thing], type: type[Thing] | None = None
    ) -> Union[MJPEGStream, Self]:
        """Return the MJPEG Stream, or the descriptor object.

        When accessed on the class, this ``__get__`` method will return the descriptor
        object. This allows LabThings to add it to the HTTP API.

        When accessed on the object, an `.MJPEGStream` is returned.

        :param obj: the host `.Thing`, or ``None`` if accessed on the class.
        :param type: the class on which we are defined.

        :return: an `.MJPEGStream`, or this descriptor.
        """
        if obj is None:
            return self
        try:
            return obj.__dict__[self.name]
        except KeyError:
            obj.__dict__[self.name] = MJPEGStream(**self._kwargs)
            return obj.__dict__[self.name]

    async def viewer_page(self, url: str) -> HTMLResponse:
        """Generate a trivial viewer page for the stream.

        :param url: the URL of the stream.

        :return: a trivial HTML page that views the stream.
        """
        return HTMLResponse(f"<html><body><img src='{url}'></body></html>")

    def add_to_fastapi(self, app: FastAPI, thing: Thing) -> None:
        """Add the stream to the FastAPI app.

        We create two endpoints, one for the MJPEG stream (using the name of
        the descriptor, relative to the host `.Thing`) and one serving a
        basic viewer.

        The example code below would create endpoints at ``/camera/stream``
        and ``/camera/stream/viewer``.

        .. code-block:: python

            import labthings_fastapi as lt


            class Camera(lt.Thing):
                stream = MJPEGStreamDescriptor()


            server = lt.ThingServer()
            server.add_thing(Camera(), "/camera")

        :param app: the `fastapi.FastAPI` application to which we are being added.
        :param thing: the host `.Thing` instance.
        """
        app.get(
            f"{thing.path}{self.name}",
            response_class=MJPEGStreamResponse,
        )(self.__get__(thing).mjpeg_stream_response)

        @app.get(
            f"{thing.path}{self.name}/viewer",
            response_class=HTMLResponse,
        )
        async def viewer_page() -> HTMLResponse:
            return await self.viewer_page(f"{thing.path}{self.name}")
