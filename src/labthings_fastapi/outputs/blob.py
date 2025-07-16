"""
# BLOB Output Module

The BlobOutput class is used when you need to return something file-like that can't
easily (or efficiently) be converted to JSON. This is useful for returning large objects
like images, especially where an existing file-type is the obvious way to handle it.

There is a [dedicated documentation page on blobs](/blobs.rst) that explains how to use
this mechanism.

To return a file from an action, you should declare its return type as a BlobOutput
subclass, defining the
[`media_type`](#labthings_fastapi.outputs.blob.Blob.media_type) attribute.

```python
class MyImageBlob(Blob):
    media_type = "image/png"

class MyThing(Thing):
    @thing_action
    def get_image(self) -> MyImageBlob:
        # Do something to get the image data
        data = self._get_image_data()
        return MyImageBlob.from_bytes(data)
```

The action should then return an instance of that subclass, with data supplied
either as a `bytes` object or a file on disk. If files are used, it's your
responsibility to ensure the file is deleted after the
[`Blob`](#labthings_fastapi.outputs.blob.Blob) object is
garbage-collected. Constructing it using the class methods
[`from_bytes`](#labthings_fastapi.outputs.blob.Blob.from_bytes) or
[`from_temporary_directory`](#labthings_fastapi.outputs.blob.Blob.from_temporary_directory)
will ensure this is done for you.

Bear in mind a `tempfile` object only holds a file descriptor and is not safe for
concurrent use, which does not work well with the HTTP API:
action outputs may be retrieved multiple times after the action has
completed, possibly concurrently. Creating a temp folder and making a file inside it
with
[`from_temporary_directory`](#labthings_fastapi.outputs.blob.Blob.from_temporary_directory)
is the safest way to deal with this.
"""

from __future__ import annotations
import io
import os
import shutil
from typing import (
    Literal,
    Mapping,
    Optional,
)
from weakref import WeakValueDictionary
from tempfile import TemporaryDirectory
import uuid

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from pydantic import (
    BaseModel,
    model_serializer,
)
from typing_extensions import Self, Protocol, runtime_checkable


@runtime_checkable
class BlobData(Protocol):
    """The interface for the data store of a Blob.

    [`Blob`](#labthings_fastapi.outputs.blob.Blob) objects can represent their data in various ways. Each of
    those options must provide three ways to access the data, which are the
    `content` property, the `save()` method, and the `open()` method.

    This protocol defines the interface needed by any data store used by a
    [`Blob`](#labthings_fastapi.outputs.blob.Blob).

    Objects that are used on the server will additionally need to implement the
    [`ServerSideBlobData`](#labthings_fastapi.outputs.blob.ServerSideBlobData) protocol,
    which adds a `response()` method and `id` property.
    """

    @property
    def media_type(self) -> str:
        """The MIME type of the data, e.g. 'image/png' or 'application/json'"""
        pass

    @property
    def content(self) -> bytes:
        """The data as a `bytes` object"""
        pass

    def save(self, filename: str) -> None:
        """Save the data to a file"""
        ...

    def open(self) -> io.IOBase:
        """Return a file-like object that may be read from."""
        ...


class ServerSideBlobData(BlobData, Protocol):
    """A BlobData protocol for server-side use, i.e. including `response()`

    [`Blob`](#labthings_fastapi.outputs.blob.Blob) objects returned by actions must use
    [`BlobData`](#labthings_fastapi.outputs.blob.BlobData) objects
    that can be downloaded. This protocol extends that protocol to
    include a [`response()`](#labthings_fastapi.outputs.blob.ServerSideBlobData.response) method that returns a FastAPI response object.

    See [`BlobBytes`](#labthings_fastapi.outputs.blob.BlobBytes) or
    [`BlobFile`](#labthings_fastapi.outputs.blob.BlobFile) for concrete implementations.
    """

    id: Optional[uuid.UUID] = None
    """A unique identifier for this BlobData object.
    
    The ID is set when the BlobData object is added to the BlobDataManager.
    It is used to retrieve the BlobData object from the manager.
    """

    def response(self) -> Response:
        """A :class:`fastapi.Response` object that sends binary data."""
        ...


class BlobBytes:
    """A BlobOutput that holds its data in memory as a :class:`bytes` object"""

    id: Optional[uuid.UUID] = None

    def __init__(self, data: bytes, media_type: str):
        self._bytes = data
        self.media_type = media_type

    @property
    def content(self) -> bytes:
        return self._bytes

    def save(self, filename: str) -> None:
        with open(filename, "wb") as f:
            f.write(self._bytes)

    def open(self) -> io.IOBase:
        return io.BytesIO(self._bytes)

    def response(self) -> Response:
        return Response(content=self._bytes, media_type=self.media_type)


class BlobFile:
    """A BlobOutput that holds its data in a file

    Only the filepath is retained by default. If you are using e.g. a temporary
    directory, you should add the temporary directory as a property, to stop it
    being garbage collected."""

    id: Optional[uuid.UUID] = None

    def __init__(self, file_path: str, media_type: str, **kwargs):
        if not os.path.exists(file_path):
            raise IOError("Tried to return a file that doesn't exist.")
        self._file_path = file_path
        self.media_type = media_type
        for key, val in kwargs.items():
            setattr(self, key, val)

    @property
    def content(self) -> bytes:
        with open(self._file_path, "rb") as f:
            return f.read()

    def save(self, filename: str) -> None:
        shutil.copyfile(self._file_path, filename)

    def open(self) -> io.IOBase:
        return open(self._file_path, mode="rb")

    def response(self) -> Response:
        return FileResponse(self._file_path, media_type=self.media_type)


class Blob(BaseModel):
    """A container for binary data that may be retrieved over HTTP

    See the [documentation on blobs](/blobs.rst) for more information on how to use this class.

    A [`Blob`](#labthings_fastapi.outputs.blob.Blob) may be created
    to hold data using the class methods
    `from_bytes` or `from_temporary_directory`. The constructor will
    attempt to deserialise a Blob from a URL (see `__init__` method).

    You are strongly advised to subclass this class and specify the
    `media_type` attribute, as this will propagate to the auto-generated
    documentation.
    """

    href: str = "blob://local"
    """The URL where the data may be retrieved. This will be `blob://local`
    if the data is stored locally."""
    rel: Literal["output"] = "output"
    description: str = (
        "The output from this action is not serialised to JSON, so it must be "
        "retrieved as a file. This link will return the file."
    )
    media_type: str = "*/*"
    """The MIME type of the data. This should be overridden in subclasses."""

    _data: ServerSideBlobData
    """This object holds the data, either in memory or as a file."""

    @model_serializer(mode="plain", when_used="always")
    def to_dict(self) -> Mapping[str, str]:
        """Serialise the Blob to a dictionary and make it downloadable"""
        return {
            "href": self.href,
            "media_type": self.media_type,
            "rel": self.rel,
            "description": self.description,
        }

    @classmethod
    def default_media_type(cls) -> str:
        """The default media type.

        `Blob` should generally be subclassed to define the default media type,
        as this forms part of the auto-generated documentation. Using the
        `Blob` class directly will result in a media type of `*/*`, which makes
        it unclear what format the output is in.
        """
        return cls.model_fields["media_type"].get_default()

    @property
    def data(self) -> ServerSideBlobData:
        """The data store for this Blob

        `Blob` objects may hold their data in various ways, defined by the
        [`ServerSideBlobData`](#labthings_fastapi.outputs.blob.ServerSideBlobData)
        protocol. This property returns the data store for this `Blob`.

        If the `Blob` has not yet been downloaded, there may be no data
        held locally, in which case this function will raise a `ValueError`.

        It is recommended to use the `content` property or `save()` or `open()`
        methods rather than accessing this property directly. Those methods will
        download data if required, rather than raising an error.
        """
        if self._data is None:
            raise ValueError("This Blob has no data.")
        return self._data

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
        return self.data.content

    def save(self, filepath: str) -> None:
        """Save the output to a file.

        This may remove the need to hold the output in memory.
        """
        self.data.save(filepath)

    def open(self) -> io.IOBase:
        """Open the output as a binary file-like object."""
        return self.data.open()

    @classmethod
    def from_bytes(cls, data: bytes) -> Self:
        """Create a BlobOutput from a bytes object"""
        return cls.model_construct(
            _data=BlobBytes(data, media_type=cls.default_media_type())
        )

    @classmethod
    def from_temporary_directory(cls, folder: TemporaryDirectory, file: str) -> Self:
        """Create a BlobOutput from a file in a temporary directory

        The TemporaryDirectory object will persist as long as this BlobOutput does,
        which will prevent it from being cleaned up until the object is garbage
        collected.
        """
        file_path = os.path.join(folder.name, file)
        return cls.model_construct(
            _data=BlobFile(
                file_path,
                media_type=cls.default_media_type(),
                # Prevent the temporary directory from being cleaned up
                _temporary_directory=folder,
            ),
        )

    @classmethod
    def from_file(cls, file: str) -> Self:
        """Create a BlobOutput from a regular file

        The file should exist for at least as long as the BlobOutput does; this
        is assumed to be the case and nothing is done to ensure it's not
        temporary. If you are using temporary files, consider creating your
        Blob with `from_temporary_directory` instead.
        """
        return cls.model_construct(
            _data=BlobFile(file, media_type=cls.default_media_type())
        )

    def response(self):
        """ "Return a suitable response for serving the output"""
        return self.data.response()


class BlobDataManager:
    """A class to manage BlobData objects

    The `BlobManager` is responsible for serving `Blob` objects to clients. It
    holds weak references: it will not retain `Blob`s that are no longer in use.
    Most `Blob`s will be retained by the output of an action: this holds a strong
    reference, and will be expired by the
    [`ActionManager`](#labthings_fastapi.actions.ActionManager).
    """

    _blobs: WeakValueDictionary[uuid.UUID, ServerSideBlobData]

    def __init__(self):
        self._blobs = WeakValueDictionary()

    def add_blob(self, blob: ServerSideBlobData) -> uuid.UUID:
        """Add a BlobOutput to the manager, generating a unique ID"""
        if hasattr(blob, "id") and blob.id is not None:
            if blob.id in self._blobs:
                return blob.id
            else:
                raise ValueError(
                    f"BlobData already has an ID {blob.id} "
                    "but was not found in this BlobDataManager"
                )
        blob.id = uuid.uuid4()
        self._blobs[blob.id] = blob
        return blob.id

    def get_blob(self, blob_id: uuid.UUID) -> ServerSideBlobData:
        """Retrieve a BlobOutput from the manager"""
        return self._blobs[blob_id]

    def download_blob(self, blob_id: uuid.UUID):
        """Download a BlobOutput"""
        blob = self.get_blob(blob_id)
        return blob.response()

    def attach_to_app(self, app: FastAPI):
        """Attach the BlobDataManager to a FastAPI app"""
        app.get("/blob/{blob_id}")(self.download_blob)
