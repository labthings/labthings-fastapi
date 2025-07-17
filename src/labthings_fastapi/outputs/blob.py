"""BLOB Output Module.

The ``.Blob`` class is used when you need to return something file-like that can't
easily (or efficiently) be converted to JSON. This is useful for returning large objects
like images, especially where an existing file-type is the obvious way to handle it.

There is a documentation page on :ref:`blobs` that explains how to use
this mechanism.

To return a file from an action, you should declare its return type as a `.Blob`
subclass, defining the
`.Blob.media_type` attribute.

.. code-block:: python

    class MyImageBlob(Blob):
        media_type = "image/png"


    class MyThing(Thing):
        @thing_action
        def get_image(self) -> MyImageBlob:
            # Do something to get the image data
            data = self._get_image_data()
            return MyImageBlob.from_bytes(data)

The action should then return an instance of that subclass, with data supplied
either as a `bytes` object or a file on disk. If files are used, it's your
responsibility to ensure the file is deleted after the
`.Blob` object is garbage-collected. Constructing it using the class methods
`.Blob.from_bytes` or `.Blob.from_temporary_directory` will ensure this is
done for you.

Bear in mind a `tempfile.TemporaryFile` object only holds a file descriptor
and is not safe for concurrent use, which does not work well with the HTTP API:
action outputs may be retrieved multiple times after the action has
completed, possibly concurrently. Creating a temp folder and making a file inside it
with `.Blob.from_temporary_directory` is the safest way to deal with this.
"""

from __future__ import annotations
from contextvars import ContextVar
import io
import os
import re
import shutil
from typing import (
    Annotated,
    AsyncGenerator,
    Callable,
    Literal,
    Mapping,
    Optional,
)
from weakref import WeakValueDictionary
from typing_extensions import TypeAlias
from tempfile import TemporaryDirectory
import uuid

from fastapi import FastAPI, Depends, Request
from fastapi.responses import FileResponse, Response
from pydantic import (
    BaseModel,
    create_model,
    model_serializer,
    model_validator,
)
from labthings_fastapi.dependencies.thing_server import find_thing_server
from starlette.exceptions import HTTPException
from typing_extensions import Self, Protocol, runtime_checkable


@runtime_checkable
class BlobData(Protocol):
    """The interface for the data store of a Blob.

    `.Blob` objects can represent their data in various ways. Each of
    those options must provide three ways to access the data, which are the
    `content` property, the `save()` method, and the `open()` method.

    This protocol defines the interface needed by any data store used by a
    `.Blob`.

    Objects that are used on the server will additionally need to implement the
    [`ServerSideBlobData`](#labthings_fastapi.outputs.blob.ServerSideBlobData) protocol,
    which adds a `response()` method and `id` property.
    """

    @property
    def media_type(self) -> str:
        """The MIME type of the data, e.g. 'image/png' or 'application/json'."""
        pass

    @property
    def content(self) -> bytes:
        """The data as a `bytes` object."""
        pass

    def save(self, filename: str) -> None:
        """Save the data to a file.

        :param filename: the path where the file should be saved.
        """
        ...

    def open(self) -> io.IOBase:
        """Return a file-like object that may be read from.

        :return: an open file-like object.
        """
        ...


class ServerSideBlobData(BlobData, Protocol):
    """A BlobData protocol for server-side use, i.e. including `response()`.

    `.Blob` objects returned by actions must use `.BlobData` objects
    that can be downloaded. This protocol extends the `.BlobData` protocol to
    include a `.ServerSideBlobData.response` method that returns a
    `fastapi.Response` object.

    See `.BlobBytes` or `.BlobFile` for concrete implementations.
    """

    id: Optional[uuid.UUID] = None
    """A unique identifier for this BlobData object.

    The ID is set when the BlobData object is added to the BlobDataManager.
    It is used to retrieve the BlobData object from the manager.
    """

    def response(self) -> Response:
        """Return a`fastapi.Response` object that sends binary data.

        :return: a response that streams the data from disk or memory.
        """
        ...


class BlobBytes:
    """A `.Blob` that holds its data in memory as a `bytes` object.

    `.Blob` objects use objects conforming to the `.BlobData` protocol to
    store their data either on disk or in a file. This implements the protocol
    using a `bytes` object in memory.

    .. note::

        This class is rarely instantiated directly. It is usually best to use
        `.Blob.from_bytes` on a `.Blob` subclass.
    """

    id: Optional[uuid.UUID] = None
    """A unique ID to identify the data in a `.BlobManager`."""

    def __init__(self, data: bytes, media_type: str):
        """Create a `.BlobBytes` object.

        `.BlobBytes` objects wrap data stored in memory as `bytes`. They
        are not usually instantiated directly, but made using `.Blob.from_bytes`.

        :param data: is the data to be wrapped.
        :param media_type: is the MIME type of the data.
        """
        self._bytes = data
        self.media_type = media_type

    @property
    def content(self) -> bytes:
        """The wrapped data, as a `bytes` object."""
        return self._bytes

    def save(self, filename: str) -> None:
        """Save the wrapped data to a file.

        :param filename: where to save the data.
        """
        with open(filename, "wb") as f:
            f.write(self._bytes)

    def open(self) -> io.IOBase:
        """Return an open file-like object containing the data.

        This wraps the underlying `bytes` in an `io.BytesIO`.

        :return: an `io.BytesIO` object wrapping the data.
        """
        return io.BytesIO(self._bytes)

    def response(self) -> Response:
        """Send the underlying data over the network.

        :return: a response that streams the data from memory.
        """
        return Response(content=self._bytes, media_type=self.media_type)


class BlobFile:
    """A `.Blob` that holds its data in a file.

    `.Blob` objects use objects conforming to the `.BlobData` protocol to
    store their data either on disk or in a file. This implements the protocol
    using a file on disk.

    Only the filepath is retained by default. If you are using e.g. a temporary
    directory, you should add the `.TemporaryDirectory` as an instance attribute,
    to stop it being garbage collected. See `.Blob.from_temporary_directory`.

    .. note::

        This class is rarely instantiated directly. It is usually best to use
        `.Blob.from_temporary_directory` on a `.Blob` subclass.
    """

    id: Optional[uuid.UUID] = None
    """A unique ID to identify the data in a `.BlobManager`."""

    def __init__(self, file_path: str, media_type: str, **kwargs):
        r"""Create a `.BlobFile` to wrap data stored on disk.

        `.BlobFile` objects wrap data stored on disk as files. They
        are not usually instantiated directly, but made using
        `.Blob.from_temporary_directory` or `.Blob.from_file`.

        :param file_path: is the path to the file.
        :param media_type: is the MIME type of the data.
        :param \**kwargs: will be added to the object as instance
            attributes. This may be used to stop temporary directories
            from being garbage collected while the `.Blob` exists.

        :raises IOError: if the file specified does not exist.
        """
        if not os.path.exists(file_path):
            raise IOError("Tried to return a file that doesn't exist.")
        self._file_path = file_path
        self.media_type = media_type
        for key, val in kwargs.items():
            setattr(self, key, val)

    @property
    def content(self) -> bytes:
        """The wrapped data, as a `bytes` object in memory.

        This reads the file on disk into a `bytes` object.

        :return: the contents of the file in a `bytes` object.
        """
        with open(self._file_path, "rb") as f:
            return f.read()

    def save(self, filename: str) -> None:
        """Save the wrapped data to a file.

        `.BlobFile` objects already store their data on disk.
        Currently, this method copies the file to the given
        filename. In the future, this may change to ``move``
        for increased efficiency.

        :param filename: the path where the file should be saved.
        """
        shutil.copyfile(self._file_path, filename)

    def open(self) -> io.IOBase:
        """Return an open file-like object containing the data.

        In the case of `.BlobFile`, this is an open file handle
        to the underlying file, which is where the data is already
        stored. It is opened with mode ``"rb"`` i.e. read-only and
        binary.

        :return: an open file handle.
        """
        return open(self._file_path, mode="rb")

    def response(self) -> Response:
        """Generate a response allowing the file to be downloaded.

        :return: a response that streams the file from disk.
        """
        return FileResponse(self._file_path, media_type=self.media_type)


class Blob(BaseModel):
    """A container for binary data that may be retrieved over HTTP.

    See :ref:`blobs` for more information on how to use this class.

    A `.Blob` may be created to hold data using the class methods
    `.Blob.from_bytes`, `.Blob.from_file` or `.Blob.from_temporary_directory`.
    The constructor will attempt to deserialise a Blob from a URL
    (see `__init__` method) and is unlikely to be used except in code
    internal to LabThings.

    You are strongly advised to use a subclass of this class that specifies the
    `.Blob.media_type` attribute, as this will propagate to the auto-generated
    documentation.
    """

    href: str
    """The URL where the data may be retrieved.

    `.Blob` objects on a `.ThingServer` are assigned a URL when they are
    serialised to JSON. This allows them to be downloaded as binary data in a
    separate HTTP request.

    `.Blob` objects created by a `.ThingClient` contain a URL pointing to the
    data, which will be downloaded when it is requred.

    `.Blob` objects that store their data in a file or in memory will have the
    ``href`` attribute set to the special value `blob://local`.
    """
    media_type: str = "*/*"
    """The MIME type of the data. This should be overridden in subclasses."""
    rel: Literal["output"] = "output"
    """The relation of this link to the host object.

    Currently, `.Blob` objects are found in the output of :ref:`actions`, so they
    always have ``rel = "output"``.
    """
    description: str = (
        "The output from this action is not serialised to JSON, so it must be "
        "retrieved as a file. This link will return the file."
    )
    """This description is added to the serialised `.Blob`."""

    _data: Optional[ServerSideBlobData] = None
    """This object holds the data, either in memory or as a file.

    If `_data` is `None`, then the Blob has not been deserialised yet, and the
    `href` should point to a valid address where the data may be downloaded.
    """

    @model_validator(mode="after")
    def retrieve_data(self) -> Self:
        r"""Retrieve the data from the URL.

        When a `.Blob` is created using its constructor, `pydantic`
        will attempt to deserialise it by retrieving the data from the URL
        specified in `.Blob.href`. Currently, this must be a URL pointing to a
        `.Blob` that already exists on this server, and any other URL will
        cause a `LookupError`.

        This validator will only work if the function to resolve URLs to
        `.BlobData` objects
        has been set in the context variable `.blob.url_to_blobdata_ctx`\ .
        This is done when actions are being invoked over HTTP by the
        `.BlobIOContextDep` dependency.

        :return: the `.Blob` object (i.e. ``self``), after retrieving the data.

        :raises ValueError: if the ``href`` is set as ``"blob://local"`` but
            the ``_data`` attribute has not been set. This happens when the
            `.Blob` is being constructed using `.Blob.from_bytes` or similar.
        :raises LookupError: if the `.Blob` is being constructed from a URL
            and the URL does not correspond to a `.BlobData` instance that
            exists on this server (i.e. one that has been previously created
            and added to the `.BlobManager` as the result of a previous action).
        """
        if self.href == "blob://local":
            if self._data:
                return self
            raise ValueError("Blob objects must have data if the href is blob://local")
        try:
            url_to_blobdata = url_to_blobdata_ctx.get()
            self._data = url_to_blobdata(self.href)
            self.href = "blob://local"
        except LookupError:
            raise LookupError(
                "Blobs may only be created from URLs passed in over HTTP."
                f"The URL in question was {self.href}."
            )
        return self

    @model_serializer(mode="plain", when_used="always")
    def to_dict(self) -> Mapping[str, str]:
        r"""Serialise the Blob to a dictionary and make it downloadable.

        When `pydantic` serialises this object,
        it will call this method to convert it to a dictionary. There is a
        significant side-effect, which is that we will add the blob to the
        `.BlobDataManager` so it can be downloaded.

        This serialiser will only work if the function to assign URLs to
        `.BlobData` objects has been set in the context variable
        `.blobdata_to_url_ctx`\ .
        This is done when actions are being returned over HTTP by the
        `.BlobIOContextDep` dependency.

        :return: a JSON-serialisable dictionary with a URL that allows
            the `.Blob` to be downloaded from the `.BlobManager`.

        :raises LookupError: if the context variable providing access to the
            `.BlobManager` is not available. This usually means the `.Blob` is
            being serialised somewhere other than the output of an action.
        """
        if self.href == "blob://local":
            try:
                blobdata_to_url = blobdata_to_url_ctx.get()
                # MyPy seems to miss that `self.data` is a property, hence the ignore
                href = blobdata_to_url(self.data)  # type: ignore[arg-type]
            except LookupError:
                raise LookupError(
                    "Blobs may only be serialised inside the "
                    "context created by BlobIOContextDep."
                )
        else:
            href = self.href
        return {
            "href": href,
            "media_type": self.media_type,
            "rel": self.rel,
            "description": self.description,
        }

    @classmethod
    def default_media_type(cls) -> str:
        """Return the default media type.

        `.Blob` should generally be subclassed to define the default media type,
        as this forms part of the auto-generated documentation. Using the
        `.Blob` class directly will result in a media type of `*/*`, which makes
        it unclear what format the output is in.

        :return: the default media type as a MIME type string, e.g. ``image/png``.
        """
        return cls.model_fields["media_type"].get_default()

    @property
    def data(self) -> ServerSideBlobData:
        """The data store for this Blob.

        `.Blob` objects may hold their data in various ways, defined by the
        `.ServerSideBlobData` protocol. This property returns the data store
        for this `.Blob`.

        If the `.Blob` has not yet been downloaded, there may be no data
        held locally, in which case this function will raise an exception.

        It is recommended to use the `.Blob.content` property or `.Blob.save`
        or `.Blob.open`
        methods rather than accessing this property directly.

        :return: the data store wrapping data on disk or in memory.

        :raises  ValueError: if there is no data stored on disk or in memory.
        """
        if self._data is None:
            raise ValueError("This Blob has no data.")
        return self._data

    @property
    def content(self) -> bytes:
        """Return the the output as a `bytes` object.

        This property may return the `bytes` object, or if we have a file it
        will read the file and return the contents. Client objects may use
        this property to download the output.

        This property is read-only. You should also only read it once, as no
        guarantees are given about cacheing - reading it many times risks
        reading the file from disk many times, or re-downloading an artifact.

        :return: a `bytes` object containing the data.
        """
        return self.data.content

    def save(self, filepath: str) -> None:
        """Save the output to a file.

        This may remove the need to hold the output in memory, especially
        if it is already stored on disk.

        :param filepath: The location to save the data on disk.
        """
        self.data.save(filepath)

    def open(self) -> io.IOBase:
        """Open the data as a binary file-like object.

        This will return a file-like object that may be read from. It may be
        either on disk (i.e. an open file handle) or in memory (e.g. an
        `io.BytesIO` wrapper).

        :return: a binary file-like object.
        """
        return self.data.open()

    @classmethod
    def from_bytes(cls, data: bytes) -> Self:
        """Create a `.Blob` from a bytes object.

        This is the recommended way to create a `.Blob` from data that is held
        in memory. It should ideally be called on a subclass that has set the
        ``media_type``.

        :param data: the data as a `bytes` object.

        :return: a `.Blob` wrapping the supplied data.
        """
        return cls.model_construct(  # type: ignore[return-value]
            href="blob://local",
            _data=BlobBytes(data, media_type=cls.default_media_type()),
        )

    @classmethod
    def from_temporary_directory(cls, folder: TemporaryDirectory, file: str) -> Self:
        """Create a `.Blob` from a file in a temporary directory.

        This is the recommended way to create a `.Blob` from data that is
        saved to a file, when the file should not be retained.
        It should ideally be called on a subclass that has set the
        ``media_type``.

        The `tempfile.TemporaryDirectory` object will persist as long as this
        `.Blob` does, which will prevent it from being cleaned up until the object
        is garbage collected. This means the file will stay on disk until it is
        no longer needed.

        :param folder: a `tempfile.TemporaryDirectory` where the file is saved.
        :param file: the path to the file, relative to the ``folder``.

        :return: a `.Blob` wrapping the file.
        """
        file_path = os.path.join(folder.name, file)
        return cls.model_construct(  # type: ignore[return-value]
            href="blob://local",
            _data=BlobFile(
                file_path,
                media_type=cls.default_media_type(),
                # Prevent the temporary directory from being cleaned up
                _temporary_directory=folder,
            ),
        )

    @classmethod
    def from_file(cls, file: str) -> Self:
        """Create a `.Blob` from a regular file.

        This is the recommended way to create a `.Blob` from a file, if that
        file will persist on disk. It should ideally be called on a subclass
        of `.Blob` that has set ``media_type``.

        .. note::

            The file should exist for at least as long as the `.Blob` does; this
            is assumed to be the case and nothing is done to ensure it's not
            temporary. If you are using temporary files, consider creating your
            `.Blob` with `from_temporary_directory` instead.

        :param file: is the path to the file. This file must exist.

        :return: a `.Blob` object referencing the specified file.
        """
        return cls.model_construct(  # type: ignore[return-value]
            href="blob://local",
            _data=BlobFile(file, media_type=cls.default_media_type()),
        )

    def response(self) -> Response:
        """Return a suitable response for serving the output.

        This method is called by the `.ThingServer` to generate a response
        that returns the data over HTTP.

        :return: an HTTP response that streams data from memory or file.
        """
        return self.data.response()


def blob_type(media_type: str) -> type[Blob]:
    r"""Create a `.Blob` subclass for a given media type.

    This convenience function may confuse static type checkers, so it is usually
    clearer to make a subclass instead, e.g.:

    .. code-block:: python

        class MyImageBlob(Blob):
            media_type = "image/png"

    :param media_type: will be the default value of the ``media_type`` property
        on the `.Blob` subclass.

    :return: a subclass of `.Blob` with the specified default media type.

    :raises ValueError: if the media type contains ``'`` or ``\``.
    """
    if "'" in media_type or "\\" in media_type:
        raise ValueError("media_type must not contain single quotes or backslashes")
    return create_model(
        f"{media_type.replace('/', '_')}_blob",
        __base__=Blob,
        media_type=(eval(f"Literal[r'{media_type}']"), media_type),
    )


class BlobDataManager:
    r"""A class to manage BlobData objects.

    The `.BlobManager` is responsible for serving `.Blob` objects to clients. It
    holds weak references: it will not retain `.Blob`\ s that are no longer in use.
    Most `.Blob`\ s will be retained by the output of an action: this holds a strong
    reference, and will be expired by the `.ActionManager`.

    Note that the `.BlobDataManager` does not work with `.Blob` objects directly,
    it holds only the `.ServerSideBlobData` object, which is where the data is
    stored. This means you should not rely on any custom attributes of a `.Blob`
    subclass being preserved when the `.Blob` is passed from one action to another.

    See :ref:`blobs` for an overview of how `.Blob` objects should be used.
    """

    def __init__(self) -> None:
        """Initialise a BlobDataManager object."""
        self._blobs: WeakValueDictionary[uuid.UUID, ServerSideBlobData] = (
            WeakValueDictionary()
        )

    def add_blob(self, blob: ServerSideBlobData) -> uuid.UUID:
        """Add a `.Blob` to the manager, generating a unique ID.

        This function adds a `.ServerSideBlobData` object to the
        `.BlobDataManager`. It will retain a weak reference to the
        `.ServerSideBlobData` object: you are responsible for ensuring
        the data is not garbage collected, for example by including the
        parent `.Blob` in the output of an action.

        :param blob: a `.ServerSideBlobData` object that holds the data
            being added.

        :return: a unique ID identifying the data. This forms part of
            the URL to download the data.

        :raises ValueError: if the `.ServerSideBlobData` object already
            has an ``id`` attribute but is not in the dictionary of
            data. This suggests the object has been added to another
            `.BlobDataManager`, which should never happen.
        """
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
        """Retrieve a `.Blob` from the manager.

        :param blob_id: the unique ID assigned when the data was added to
            this `.BlobDataManager`.

        :return: the `.ServerSideBlobData` object holding the data.
        """
        return self._blobs[blob_id]

    def download_blob(self, blob_id: uuid.UUID) -> Response:
        """Download a `.Blob`.

        This function returns a `fastapi.Response` allowing the data to be
        downloaded, using the `.ServerSideBlobData.response` method.

        :param blob_id: the unique ID assigned when the data was added to
            this `.BlobDataManager`.

        :return: a `fastapi.Response` object that will send the content of
            the blob over HTTP.
        """
        blob = self.get_blob(blob_id)
        return blob.response()

    def attach_to_app(self, app: FastAPI) -> None:
        """Attach the BlobDataManager to a FastAPI app.

        Add an endpoint to a FastAPI application that will serve the content of
        the `.ServerSideBlobData` objects in response to ``GET`` requests.

        :param app: the `fastapi.FastAPI` application to which we are adding
            the endpoint.
        """
        app.get("/blob/{blob_id}")(self.download_blob)


blobdata_to_url_ctx = ContextVar[Callable[[ServerSideBlobData], str]]("blobdata_to_url")
"""This context variable gives access to a function that makes BlobData objects
downloadable, by assigning a URL and adding them to the
[`BlobDataManager`](#labthings_fastapi.outputs.blob.BlobDataManager).

It is only available within a
[`blob_serialisation_context_manager`](#labthings_fastapi.outputs.blob.blob_serialisation_context_manager)
because it requires access to the `BlobDataManager` and the `url_for` function
from the FastAPI app.
"""

url_to_blobdata_ctx = ContextVar[Callable[[str], ServerSideBlobData]]("url_to_blobdata")
"""This context variable gives access to a function that makes BlobData objects
from a URL, by retrieving them from the
[`BlobDataManager`](#labthings_fastapi.outputs.blob.BlobDataManager).

It is only available within a
[`blob_serialisation_context_manager`](#labthings_fastapi.outputs.blob.blob_serialisation_context_manager)
because it requires access to the `BlobDataManager`.
"""


async def blob_serialisation_context_manager(
    request: Request,
) -> AsyncGenerator[BlobDataManager]:
    r"""Set context variables to allow blobs to be [de]serialised.

    In order to serialise a `.Blob` to a JSON-serialisable dictionary, we must
    add it to the `.BlobDataManager` and use that to generate a URL. This
    requres that the serialisation code (which may be nested deep within a
    `pydantic.BaseModel`) has access to the `.BlobDataManager` and also the
    `fastapi.Request.url_for` method. At time of writing, there was not an
    obvious way to pass these functions in to the serialisation code.

    Similar problems exist for blobs used as input: the validator needs to
    retrieve the data from the `.BlobDataManager` but does not have access.

    This async context manager yields the `.BlobDataManager`, but more
    importantly it sets the `.url_to_blobdata_ctx` and `blobdata_to_url_ctx`
    context variables, which may be accessed by the code within `.Blob` to
    correctly add and retrieve `.ServerSideBlobData` objects to and from the
    `.BlobDataManager`\ .

    This function will usually be called from a FastAPI dependency. See
    :ref:`dependencies` for more on that mechanism.

    :param request: the `fastapi.Request` object, used to access the server
        and ``url_for`` method.

    :yield: the `.BlobDataManager`. This is usually ignored.
    """
    thing_server = find_thing_server(request.app)
    blob_manager: BlobDataManager = thing_server.blob_data_manager
    url_for = request.url_for

    def blobdata_to_url(blob: ServerSideBlobData) -> str:
        blob_id = blob_manager.add_blob(blob)
        return str(url_for("download_blob", blob_id=blob_id))

    def url_to_blobdata(url: str) -> ServerSideBlobData:
        m = re.search(r"blob/([0-9a-z\-]+)", url)
        if not m:
            raise HTTPException(
                status_code=404, detail="Could not find blob ID in href"
            )
        invocation_id = uuid.UUID(m.group(1))
        return blob_manager.get_blob(invocation_id)

    t1 = blobdata_to_url_ctx.set(blobdata_to_url)
    t2 = url_to_blobdata_ctx.set(url_to_blobdata)
    try:
        yield blob_manager
    finally:
        blobdata_to_url_ctx.reset(t1)
        url_to_blobdata_ctx.reset(t2)


BlobIOContextDep: TypeAlias = Annotated[
    BlobDataManager, Depends(blob_serialisation_context_manager)
]
"""A dependency that enables `.Blob` to be serialised and deserialised."""
