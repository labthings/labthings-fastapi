import logging
import time
from labthings_fastapi.thing import Thing
from labthings_fastapi.decorators import thing_action
from labthings_fastapi.thing_server import ThingServer
from labthings_fastapi.descriptors import PropertyDescriptor
from labthings_fastapi.file_manager import FileManager
from threading import RLock
import numpy as np
import cv2 as cv

logging.basicConfig(level=logging.INFO)

class OpenCVCamera(Thing):
    """A Thing that represents an OpenCV camera"""
    def __init__(self, device_index: int = 0):
        self.device_index = device_index
        
    def __enter__(self):
        self._cap = cv.VideoCapture(self.device_index)
        self._cap_lock = RLock()
        if not self._cap.isOpened():
            raise IOError(f"Cannot open camera with device index {self.device_index}")
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        self._cap.release()
        del self._cap
        del self._cap_lock

    @thing_action
    def snap_image(self, file_manager: FileManager) -> str:
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

    
thing_server = ThingServer()
my_thing = OpenCVCamera()
print(my_thing.validate_thing_description())
thing_server.add_thing(my_thing, "/camera")

app = thing_server.app