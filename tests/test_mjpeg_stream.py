import io
import threading
import time
from PIL import Image
from fastapi.testclient import TestClient
import labthings_fastapi as lt


class Telly(lt.Thing):
    _stream_thread: threading.Thread
    _streaming: bool = False
    framerate: float = 1000

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

        i = -1
        start_time = time.time()
        while self._streaming:
            i = (i + 1) % len(jpegs)
            print(f"sending frame {i}")
            self.stream.add_frame(jpegs[i], self._labthings_blocking_portal)
            time.sleep(1 / self.framerate)

            if time.time() - start_time > 10:
                break
        print("stopped sending frames")
        self._streaming = False


def test_mjpeg_stream():
    server = lt.ThingServer()
    telly = Telly()
    server.add_thing(telly, "telly")
    with TestClient(server.app) as client:
        with client.stream("GET", "/telly/stream", timeout=0.1) as stream:
            stream.raise_for_status()
            received = 0
            for b in stream.iter_bytes():
                received += 1
                print(f"Got packet {received}")
                assert b.startswith(b"--frame")
                if received > 5:
                    break


if __name__ == "__main__":
    test_mjpeg_stream()
