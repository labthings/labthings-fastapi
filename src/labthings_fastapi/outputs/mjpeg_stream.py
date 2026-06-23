"""MJPEG Stream support.

This module defines a descriptor that allows `~lt.Thing` subclasses to expose an
MJPEG stream. See `.MJPEGStreamDescriptor`.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncGenerator,
    Literal,
    Optional,
    Union,
    overload,
)
from weakref import WeakSet

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from typing_extensions import Self

from labthings_fastapi.message_broker import MessageBroker

if TYPE_CHECKING:
    from labthings_fastapi.thing import Thing
    from labthings_fastapi.thing_server_interface import ThingServerInterface


LOGGER = logging.getLogger(__name__)


@dataclass
class Frame:
    """A single frame in a ringbuffer.

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

    def __init__(
        self,
        send_stream: MemoryObjectSendStream[Frame],
        receive_stream: MemoryObjectReceiveStream[Frame],
        status_code: int = 200,
    ) -> None:
        """Set up StreamingResponse that streams an MJPEG stream.

        This response is initialised with an async generator that yields `bytes`
        objects, each of which is a JPEG file. We add the --frame markers and mime
        types that mark it as an MJPEG stream. This is sufficient to enable it to
        work in an `img` tag, with the `src` set to the MJPEG stream's endpoint.

        It expects an async generator that supplies individual JPEGs to be streamed,
        such as the one provided by `.MJPEGStream`.

        NB the ``status_code`` argument is used by FastAPI to set the status code of
        the response in OpenAPI.

        :param send_stream: the stream used to send `Frame` objects (this must be
            retained or it will be garbage collected).
        :param receive_stream: a stream that will receive `Frame` objects.
        :param status_code: The status code associated with the response, by default
            a 200 code is returned.
        """
        self._send_stream = send_stream
        self._receive_stream = receive_stream
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

        We use three `yield` statements in order to avoid concatenating
        (and thus copying) `bytes` objects.

        :yield: JPEG frames, each with a ``--frame`` marker prepended.
        """
        async for frame in self._receive_stream:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
            yield frame.frame
            yield b"\r\n"


class MJPEGStream:
    """Manage streaming images over HTTP as an MJPEG stream.

    An MJPEGStream object handles accepting images (already in
    JPEG format) and streaming them to HTTP clients as a multipart
    response.

    The minimum needed to make the stream work is to periodically
    call `add_frame` with JPEG image data.

    To add a stream to a `~lt.Thing`, use the `.MJPEGStreamDescriptor`
    which will handle creating an `.MJPEGStream` object on first access,
    and will also add it to the HTTP API.
    """

    def __init__(self, thing_server_interface: ThingServerInterface) -> None:
        """Initialise an MJPEG stream.

        See the class docstring for `.MJPEGStream`. Note that it will
        often be initialised by `.MJPEGStreamDescriptor`.

        :param thing_server_interface: the `~lt.ThingServerInterface` of the
            `~lt.Thing` associated with this stream. It's used to run the async
            code that relays frames to open connections.
        """
        self._lock = threading.Lock()
        self._streaming = True
        self._subscriptions = WeakSet[MemoryObjectSendStream[Frame]]()
        self._thing_server_interface = thing_server_interface
        self.last_frame_i = -1

    def reset(self) -> None:
        """Reset the stream index."""
        with self._lock:
            self.last_frame_i = -1

    def stop(self) -> None:
        """Stop the stream.

        Stop the stream and cause all clients to disconnect.

        .. warning::

            This function must be called from a thread, not from the event loop.
            Calling it from the event loop may deadlock: use `close_streams`
            instead.
        """
        self._thing_server_interface.start_async_task_soon(self.close_streams)

    def connected_stream(
        self, max_buffer_size: int = 0
    ) -> tuple[
        MemoryObjectSendStream[Frame],
        MemoryObjectReceiveStream[Frame],
    ]:
        """Make a stream pair to receive frames.

        The "send" stream will be added to our list of subscribers. However, it must
        be retained as well as the "receive" stream. This is because the set of
        subscribers only holds weak references. Once the streams are out of scope,
        they will be finalised and unsubscribed.

        The stream will not have a buffer by default: this means any delay in reading
        it could lead to missed frames.

        :param max_buffer_size: the size of buffer to permit. This reduces the
            likelihood of dropping frames, at the expense of latency and memory.
        :return: a stream that will yield new frames.
        """
        send, receive = anyio.create_memory_object_stream[Frame](max_buffer_size)
        self._subscriptions.add(send)
        return send, receive

    async def grab_frame(self) -> bytes:
        """Wait for the next frame, and return it.

        This returns the contents of the next frame to be sent.

        :return: The next JPEG frame, as a `bytes` object.
        """
        _send, receive = self.connected_stream()
        try:
            frame = await receive.receive()
        finally:
            await receive.aclose()
        return frame.frame

    async def next_frame_size(self) -> int:
        """Wait for the next frame, and return its size.

        :return: the size of the next JPEG frame.
        """
        frame = await self.grab_frame()
        return len(frame)

    async def frame_async_generator(self) -> AsyncGenerator[bytes, None]:
        """Yield frames as bytes objects.

        This generator will return frames from the MJPEG stream as `bytes`
        objects.

        Note that this will wait for a new frame each time. There is no
        guarantee that we won't skip frames.

        :yield: the frames in sequence, as a `bytes` object containing
            JPEG data.
        """
        _send, receive = self.connected_stream()
        async for frame in receive:
            yield frame.frame

    async def mjpeg_stream_response(self) -> MJPEGStreamResponse:
        """Return a StreamingResponse that streams an MJPEG stream.

        This wraps each frame with the required header to make the
        multipart stream work, and sends it to the client via a
        streaming response. It is sufficient to show up as a video
        in an ``img`` tag, or to be streamed to disk as an MJPEG
        format video.

        :return: a streaming response in MJPEG format.
        """
        return MJPEGStreamResponse(*self.connected_stream())

    def add_frame(self, frame: bytes) -> None:
        """Add a JPEG to the MJPEG stream.

        This function adds a frame to the stream. It may be called from
        threaded code, but uses an `anyio.from_thread.BlockingPortal` to
        call code in the `anyio` event loop, which is where notifications
        are handled.

        :param frame: The frame to add. This must start and end with the JPEG
            start/end bytes.

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
            self.last_frame_i += 1
            i = self.last_frame_i
        self._thing_server_interface.start_async_task_soon(
            self.notify_new_frame,
            Frame(
                timestamp=datetime.now(),
                frame=frame,
                index=i,
            ),
        )

    async def notify_new_frame(self, frame: Frame) -> None:
        """Notify any waiting tasks that a new frame is available.

        This uses the same logic as `MessageBroker` to send new frames to a set of
        streams.

        :param frame: The new frame to circulate.
        """
        # For backwards compatibility, we check the `_streaming` flag here.
        # This is consistent with the old behaviour, which would act on it when
        # new frames were distributed.
        if not self._streaming:
            await self.close_streams()
        await MessageBroker.publish_and_prune(self._subscriptions, frame)

    async def close_streams(self) -> None:
        """Raise an exception in any waiting tasks to signal the stream has stopped."""
        for stream in self._subscriptions:
            await stream.aclose()


class MJPEGStreamDescriptor:
    """A descriptor that returns a MJPEGStream object when accessed.

    If this descriptor is added to a `~lt.Thing`, it will create an `.MJPEGStream`
    object when it is first accessed. It will also add two HTTP endpoints,
    one with the name of the descriptor serving the MJPEG stream, and another
    with `/viewer` appended, which serves a basic HTML page that views the stream.

    This descriptor does not currently show up in the :ref:`wot_td`.
    """

    def __init__(self, **kwargs: Any) -> None:
        r"""Initialise an MJPEGStreamDescriptor.

        :param \**kwargs: keyword arguments are passed to the initialiser of
            `.MJPEGStream`.
        """
        self._kwargs: Any = kwargs

    def __set_name__(self, _owner: Thing, name: str) -> None:
        """Remember the name to which we are assigned.

        The name is important, as it will set the URL of the HTTP endpoint used
        to access the stream.

        :param _owner: the `~lt.Thing` to which we are attached.
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

        :param obj: the host `~lt.Thing`, or ``None`` if accessed on the class.
        :param type: the class on which we are defined.

        :return: an `.MJPEGStream`, or this descriptor.
        """
        if obj is None:
            return self
        try:
            return obj.__dict__[self.name]
        except KeyError:
            obj.__dict__[self.name] = MJPEGStream(
                **self._kwargs,
                thing_server_interface=obj._thing_server_interface,
            )
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
        the descriptor, relative to the host `~lt.Thing`) and one serving a
        basic viewer.

        The example code below would create endpoints at ``/camera/stream``
        and ``/camera/stream/viewer``.

        .. code-block:: python

            import labthings_fastapi as lt


            class Camera(lt.Thing):
                stream = MJPEGStreamDescriptor()


            server = lt.ThingServer.from_things({"camera": Camera})

        :param app: the `fastapi.FastAPI` application to which we are being added.
        :param thing: the host `~lt.Thing` instance.
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
