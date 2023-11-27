"""BLOB Output Module

The BlobOutput class is used when you need to return something file-like that can't
easily (or efficiently) be converted to JSON. This is useful for returning large objects
like images, especially where an existing file-type is the obvious way to handle it.

To return a file from an action, you should declare its return type as a BlobOutput
subclass, defining the `media_type` attribute.

The output from the class should be an instance of that subclass, with data supplied
either as a `bytes` object or a file on disk. If files are used, it's your
responsibility to ensure the file is deleted after the `BlobOutput` object is
garbage-collected. Constructing it using the class methods `from_bytes` or
`from_temporary_directory` will ensure this is done for you.

Bear in mind a `tempfile` object only holds a file descriptor and is not safe for
concurrent use: action outputs may be retrieved multiple times after the action has
completed. Creating a temp folder and making a file inside it is the safest way to
deal with this.
"""

from __future__ import annotations
import io
import os
from typing import Any
from tempfile import TemporaryDirectory

from fastapi.responses import FileResponse, Response


def is_blob_output(obj: Any) -> bool:
    """Check if a class is a BlobOutput"""
    for attr in (
        "media_type",
        "content",
        "save_to_file",
        "open",
        "response",
    ):
        if not hasattr(obj, attr):
            return False
    return True


NEITHER_BYTES_NOR_FILE = NotImplementedError(
    "BlobOutput subclasses must provide _bytes or _file_path"
)


class BlobOutput:
    """An output from LabThings best returned as a file

    This may be instantiated either using the class methods `from_bytes` or
    `from_temporary_directory`, which will use a `bytes` object to store the
    output, or return a file on disk in a temporary directory. In the latter
    case, the temporary directory will be deleted when the object is garbage
    collected.
    """

    media_type: str
    _bytes: bytes
    _file_path: str
    _temporary_directory: TemporaryDirectory

    @property
    def content(self) -> bytes:
        """Return the the output as a `bytes` object

        This property may return the `bytes` object, or if we have a file it
        will read the file and return the contents. Client objects may use
        this property to download the output.

        This property is read-only. You should also only read it once, as no
        guarantees are given about cacheing - reading it many times risks
        reading the file from disk many times, or re-downloading an artifact.
        """
        if hasattr(self, "_bytes"):
            return self._bytes
        if hasattr(self, "_file_path"):
            with open(self._file_path, "rb") as f:
                return f.read()
        raise NEITHER_BYTES_NOR_FILE

    def save_to_file(self, filepath: str) -> None:
        """Save the output to a file.

        This may remove the need to hold the output in memory.
        """
        if hasattr(self, "_bytes"):
            with open(filepath, "wb") as f:
                f.write(self._bytes)
        if hasattr(self, "_file_path"):
            import shutil

            shutil.copyfile(self._file_path, filepath)
        raise NEITHER_BYTES_NOR_FILE

    def open(self) -> io.IOBase:
        """Open the output as a binary file-like object."""
        if hasattr(self, "_bytes"):
            return io.BytesIO(self._bytes)
        if hasattr(self, "_file_path"):
            return open(self._file_path, mode="rb")
        raise NEITHER_BYTES_NOR_FILE

    @classmethod
    def from_bytes(cls, data: bytes) -> BlobOutput:
        """Create a BlobOutput from a bytes object"""
        obj = cls()
        obj._bytes = data
        return obj

    @classmethod
    def from_temporary_directory(
        cls, folder: TemporaryDirectory, file: str
    ) -> BlobOutput:
        """Create a BlobOutput from a file in a temporary directory

        The TemporaryDirectory object will persist as long as this BlobOutput does,
        which will prevent it from being cleaned up until the object is garbage
        collected.
        """
        obj = cls()
        obj._file_path = os.path.join(folder.name, file)
        obj._temporary_directory = folder
        return obj

    def response(self):
        """ "Return a suitable response for serving the output"""
        if hasattr(self, "_bytes"):
            return Response(content=self._bytes, media_type=self.media_type)
        if hasattr(self, "_file_path"):
            return FileResponse(self._file_path, media_type=self.media_type)
        raise NEITHER_BYTES_NOR_FILE
