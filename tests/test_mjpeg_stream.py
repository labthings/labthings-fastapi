import io
import threading
import time

import pytest
from PIL import Image

import labthings_fastapi as lt


class Telly(lt.Thing):
    _stream_thread: threading.Thread
    _streaming: bool = False
    framerate: float = 1000
    frame_limit: int = 999
    frame_event: threading.Event | None = None
    initial_delay: float = 0

    stream = lt.outputs.MJPEGStreamDescriptor()

    def __enter__(self):
        self._streaming = True
        self._stream_thread = threading.Thread(target=self._make_images)
        self._stream_thread.start()

    def __exit__(self, exc_t, exc_v, exc_tb):
        self._streaming = False
        if self.frame_event:
            # Trigger an iteration of the loop, so that it
            # will terminate rather than hang forever
            self.frame_event.set()
        self._stream_thread.join()

    def _make_images(self):
        """Stream a series of solid colours"""
        colours = ["#F00", "#0F0", "#00F"]
        jpegs = []
        for c in colours:
            image = Image.new("RGB", (10, 10), c)
            dest = io.BytesIO()
            image.save(dest, "jpeg")
            jpegs.append(dest.getvalue())

        if self.initial_delay > 0:
            time.sleep(self.initial_delay)

        i = 0
        while self._streaming and (i < self.frame_limit or self.frame_limit < 0):
            self.stream.add_frame(jpegs[i % len(jpegs)])
            i = i + 1
            if self.frame_event:
                self.frame_event.wait()
                self.frame_event.clear()
            else:
                time.sleep(1 / self.framerate)
        self.stream.stop()
        self._streaming = False


def assert_magic_bytes(frame: bytes) -> None:
    """Check that a `bytes` object starts and ends with the JPEG markers."""
    assert frame[0] == 0xFF
    assert frame[1] == 0xD8
    assert frame[-2] == 0xFF
    assert frame[-1] == 0xD9


@pytest.fixture
def server():
    """Yield a ThingServer with the `Telly` thing."""
    return lt.ThingServer.from_things({"telly": Telly})


@pytest.fixture
def telly(server):
    """Yield a Telly thing from the server."""
    telly = server.things["telly"]
    assert isinstance(telly, Telly)
    return telly


def test_grab_and_shutdown(server: lt.ThingServer, telly: Telly):
    """Check we can grab frames, and shut down cleanly.

    This test uses an Event to synchronise new frames with the various
    methods we're calling to retrieve them. This is intended to make the
    test suite faster and less reliant on `time.sleep`.

    We check that `grab_frame` and `next_frame_size` both work when the
    camera emits frames, and also that they raise an error if they're called
    once the camera has stopped.

    We verify that the stream can be stopped, though we don't shut down any
    long-running listeners, because limitations in TestClient mean this
    isn't possible. It would be possible if we spun up an actual HTTP server,
    but that's quite high-effort.

    The async grab functions need to run in the event loop, which happens in
    a background thread during the `with server.test_client()` block. We use
    the thing server interface to run tasks in the event loop for convenience.
    """
    telly.frame_event = threading.Event()  # Make timings more deterministic.
    with server.test_client():
        # this `with` block starts an event loop and runs the server.

        # Grab some frames and check we get a JPEG back
        for _ in range(3):
            assert telly._stream_thread.is_alive()  # Catch premature termination
            # Start the coroutine to grab a frame
            future = telly._thing_server_interface.start_async_task_soon(
                telly.stream.grab_frame
            )
            # then use the event to trigger the next frame.
            telly.frame_event.set()
            # then wait for the coroutine to finish
            frame = future.result()
            # this should return a valid JPEG, which we can (sort of) check below
            assert_magic_bytes(frame)

        # Repeat the process for grabbing a frame to test `next_frame_size`
        future = telly._thing_server_interface.start_async_task_soon(
            telly.stream.next_frame_size
        )
        telly.frame_event.set()
        size = future.result()  # wait for the frame to be grabbed
        assert isinstance(size, int)
        assert size > 0

        # Close all streams
        telly._thing_server_interface.call_async_task(telly.stream.close_streams)

        # We shouldn't be able to get any more frames now
        # This means that the stream won't generate any new stream pairs
        with pytest.raises(StopAsyncIteration):
            telly.stream.connected_stream()
        # The grab functions depend on the function above, so they should also fail.
        with pytest.raises(StopAsyncIteration):
            telly._thing_server_interface.call_async_task(telly.stream.grab_frame)
        with pytest.raises(StopAsyncIteration):
            telly._thing_server_interface.call_async_task(telly.stream.next_frame_size)
    # The background thread gets shut down by `Telly.__exit__`.


def test_mjpeg_stream_http(server: lt.ThingServer, telly: Telly):
    """Verify the MJPEG stream works, and is shut down cleanly.

    A limitation of the TestClient is that it can't actually stream.
    This means that all of the frames sent by our test Thing will
    arrive in a single packet.

    For now, we download all the data and then chop it up afterwards.

    The `Telly` will send exactly 3 JPEGs, with a short delay at
    the start to make sure the `StreamingResponse` is created and
    doesn't miss any frames.

    This test also verifies the stream is shut down by the server
    when it's stopped - if it wasn't terminated by the server, the
    `client.stream()` call would hang indefinitely.
    """
    telly.frame_limit = 3  # stream 3 frames and then stop
    telly.initial_delay = 0.05  # give the client time to start listening
    with server.test_client() as client:
        with client.stream("GET", "/telly/stream") as response:
            # Note: we don't actually enter this `with` block until after
            # the camera background thread has finished and the stream
            # has been closed.
            response.raise_for_status()
            parts = 0
            mjpeg_data = b""
            for b in response.iter_bytes():
                parts += 1
                mjpeg_data += b
            # Due to a quirk in TestClient, we get all the data in a single
            # chunk - this limits our ability to test the stream.
            # If that's fixed in the future, the assertion below will fail,
            # which should prompt us to improve these tests.
            assert parts == 1

    # Check the received data contained the expected number of frames
    # We split chunks using the known header, and remove extra white
    # space before checking for JPEG start/end bytes.
    chunks = mjpeg_data.split(b"--frame\r\nContent-Type: image/jpeg")
    n = 0
    for chunk in chunks:
        # Check each chunk is a JPEG
        stripped = chunk.strip(b"\r\n")
        if len(stripped) > 10:  # If the chunk doesn't look empty
            assert_magic_bytes(stripped)
            n += 1
    assert telly.stream.last_frame_i == 2
    assert n == telly.frame_limit


if __name__ == "__main__":
    """This block allows you to connect manually with a web browser.
    
    That's helpful, because the tests above don't actually stream anything
    as noted in `test_mjpeg_stream_http`.
    """
    thing_server = lt.ThingServer.from_things({"telly": Telly})
    telly = thing_server.things["telly"]
    assert isinstance(telly, Telly)
    telly.framerate = 6
    telly.frame_limit = -1
    thing_server.serve()
