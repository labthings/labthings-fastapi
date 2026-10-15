"""MJPEG Stream support.

This module defines a descriptor that allows `~lt.Thing` subclasses to expose an
MJPEG stream. See `.MJPEGStreamDescriptor`.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from typing import (
    Any,
    AsyncGenerator,
    Optional,
)

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse

from labthings_fastapi.base_descriptor import BaseDescriptor
from labthings_fastapi.message_broker import Message, MessageBroker
from labthings_fastapi.thing import Thing


@dataclass
class Frame:
    """A single frame in the stream.

    This structure comprises one frame as a JPEG, plus a timestamp and
    a buffer index. Each time a frame is added to the stream, it is
    tagged with a timestamp and index, with the index increasing by
    1 each time.
    """

    frame: bytes
    """The frame as a `bytes` object, which is a JPEG image for an MJPEG stream."""

    timestamp: datetime
    """The time the frame was captured.
    If the capture time is unknown then the timestamp is
    the time that the frame was added to the ringbuffer."""

    index: int
    """The index of the frame within the stream."""

    def __repr__(self) -> str:
        """Represent the object as a string.

        :return: a representation of the object as a string.
        """
        return (
            f"Frame(index={self.index}, timestamp={self.timestamp}, "
            f"frame=<{len(self.frame)} bytes>)"
        )


def check_jpeg_bytes(frame: bytes) -> bool:
    """Check a JPEG file starts and ends with the right magic bytes.

    :param frame: the data, which should be in JPEG format.
    :return: `True` if the data is a valid JPEG (i.e. has valid start/end bytes).
    """
    return (
        frame[0] == 0xFF
        and frame[1] == 0xD8
        and frame[-2] == 0xFF
        and frame[-1] == 0xD9
    )


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
        self, gen: AsyncGenerator[bytes, None], status_code: int = 200
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

        :param gen: an async generator, yielding `bytes` objects each of which is
            one image, in JPEG format.
        :param status_code: The status code associated with the response, by default
            a 200 code is returned.
        """
        self._frame_async_generator = gen
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
        async for frame in self._frame_async_generator:
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

    To add a stream to a `~lt.Thing`, use the `.MJPEGStreamDescriptor`
    which will handle creating an `.MJPEGStream` object on first access,
    and will also add it to the HTTP API.

    The MJPEG stream buffers the last few frames (10 by default) and
    also has a hook to notify the size of each frame as it is added.
    The latter is used by OpenFlexure's autofocus routine. The
    ringbuffer is intended to support clients receiving notification
    of new frames, and then retrieving the frame (shortly) afterwards.
    """

    def __init__(self, thing: Thing, name: str) -> None:
        """Initialise an MJPEG stream.

        See the class docstring for `.MJPEGStream`. Note that it will
        often be initialised by `.MJPEGStreamDescriptor`.

        :param thing: the `~lt.Thing` on which this stream is defined.
        :param name: The attribute name of this stream.
        """
        self._lock = threading.Lock()
        self._thing = thing
        self._name = name
        self.reset()

    @property
    def _broker(self) -> MessageBroker:
        """The message broker associated with our host Thing."""
        return self._thing._thing_server_interface.message_broker

    def reset(self) -> None:
        """Reset the frame index."""
        with self._lock:
            self.last_frame_i = -1

    def stop(self) -> None:
        """Stop the stream.

        Stop the stream and cause all clients to disconnect.
        This uses the thing server interface to allow it to be called from
        a thread, for convenience.

        To close all streams from the event loop, use the message broker directly.
        """
        self._thing._thing_server_interface.call_async_task(
            self._broker.close_streams_for_affordance,
            self._thing.name,
            self._name,
        )

    async def frames(self) -> AsyncGenerator[Frame, None]:
        """Yield Frame objects (data and metadata).

        This generator will return frames from the MJPEG stream along with timestamps,
        using the `Frame` dataclass.

        Note that this will wait for a new frame each time. There is no
        guarantee that we won't skip frames. There's no timeout, if the MJPEG stream
        doesn't get new frames this may block indefinitely.

        :yield: the frames in sequence.
        """
        async for message in self._broker.messages_for_affordance(
            self._thing.name, self._name
        ):
            if isinstance(message.payload, Frame):
                # We simply ignore messages that don't contain Frame objects.
                # We don't expect to get any payloads that are not Frame objects.
                yield message.payload

    async def frame_async_generator(self) -> AsyncGenerator[bytes, None]:
        """Yield frames as bytes objects.

        This generator will return frames from the MJPEG stream.

        See `frames` for how this works. This function wraps that one, returning
        only the `bytes` object rather than the full `Frame` dataclass which also
        includes metadata.

        :yield: the frames in sequence, as a `bytes` object containing
            JPEG data.
        """
        async for frame in self.frames():
            yield frame.frame

    async def grab_frame_with_metadata(self) -> Frame:
        """Wait for the next frame, and return it.

        This includes metadata such as the timestamp.

        This method calls `frames` and returns the first frame that's yielded.

        :return: The next JPEG frame, in a dataclass with metadata.
        """
        return await anext(self.frames())

    async def grab_frame(self) -> bytes:
        """Wait for the next frame, and return it.

        :return: The next JPEG frame, as a `bytes` object.
        """
        payload = await self.grab_frame_with_metadata()
        return payload.frame

    async def next_frame_size(self) -> int:
        """Wait for the next frame and return its size.

        This is useful if you want to use JPEG size as a sharpness metric.

        :return: The size of the next JPEG frame, in bytes.
        """
        return len(await self.grab_frame())

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

    def add_frame(self, frame: bytes, timestamp: Optional[datetime] = None) -> None:
        """Add a JPEG to the MJPEG stream.

        This function adds a frame to the stream. It may be called from
        threaded code, but uses an `anyio.from_thread.BlockingPortal` to
        call code in the `anyio` event loop, which is where notifications
        are handled.

        :param frame: The frame to add
        :param timestamp: The time the frame was captured. If not supplied,
            the timestamp falls back to the time the frame  was added to the
            ringbuffer.

        :raise ValueError: if the supplied frame does not start with the JPEG
            start bytes and end with the end bytes.
        """
        if not check_jpeg_bytes(frame):
            raise ValueError("Invalid JPEG")
        with self._lock:
            self.last_frame_i += 1
            frame_index = self.last_frame_i
        payload = Frame(
            frame=frame,
            timestamp=timestamp if timestamp is not None else datetime.now(),
            index=frame_index,
        )
        self._thing._thing_server_interface.publish(
            Message(self._thing.name, self._name, "stream", payload)
        )


class MJPEGStreamDescriptor(BaseDescriptor[Thing, MJPEGStream]):
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
        super().__init__()
        self._kwargs: Any = kwargs

    def instance_get(self, obj: Thing) -> MJPEGStream:
        """Return the MJPEG Stream.

        :param obj: the host `~lt.Thing`.

        :return: an `.MJPEGStream`, or this descriptor.
        """
        try:
            return obj.__dict__[self.name]
        except KeyError:
            obj.__dict__[self.name] = MJPEGStream(
                thing=obj,
                name=self.name,
                **self._kwargs,
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
