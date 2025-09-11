import io
import threading
import time
from PIL import Image
from fastapi.testclient import TestClient
import pytest
import labthings_fastapi as lt


class Telly(lt.Thing):
    _stream_thread: threading.Thread
    _streaming: bool = False
    framerate: float = 1000
    frame_limit: int = 3

    stream = lt.outputs.MJPEGStreamDescriptor()

    def __enter__(self):
        self._streaming = True
        self._stream_thread = threading.Thread(target=self._make_images)
        self._stream_thread.start()

    def __exit__(self, exc_t, exc_v, exc_tb):
        self._streaming = False
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

        i = 0
        while self._streaming and (i < self.frame_limit or self.frame_limit < 0):
            self.stream.add_frame(
                jpegs[i % len(jpegs)], self._labthings_blocking_portal
            )
            time.sleep(1 / self.framerate)
            i = i + 1
        self.stream.stop(self._labthings_blocking_portal)
        self._streaming = False


@pytest.fixture
def client():
    """Yield a test client connected to a ThingServer"""
    server = lt.ThingServer()
    server.add_thing("telly", Telly)
    with TestClient(server.app) as client:
        yield client


def test_mjpeg_stream(client):
    """Verify the MJPEG stream contains at least one frame marker.

    A limitation of the TestClient is that it can't actually stream.
    This means that all of the frames sent by our test Thing will
    arrive in a single packet.

    For now, we just check it starts with the frame separator,
    but it might be possible in the future to check there are three
    images there.
    """
    with client.stream("GET", "/telly/stream") as stream:
        stream.raise_for_status()
        received = 0
        for b in stream.iter_bytes():
            received += 1
            assert b.startswith(b"--frame")


if __name__ == "__main__":
    import uvicorn

    server = lt.ThingServer()
    telly = server.add_thing("telly", Telly)
    telly.framerate = 6
    telly.frame_limit = -1
    uvicorn.run(server.app, port=5000)
