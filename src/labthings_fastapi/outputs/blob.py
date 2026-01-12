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
        @action
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
from collections.abc import Callable
import io
import os
import re
import shutil
from typing import (
    Any,
    Literal,
    Mapping,
)
from warnings import warn
from weakref import WeakValueDictionary
from tempfile import TemporaryDirectory
import uuid

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
import httpx
from pydantic import (
    BaseModel,
    GetCoreSchemaHandler,
)
from pydantic_core import core_schema
from typing_extensions import Self
from labthings_fastapi.middleware.url_for import url_for


class BlobData:
    """The data store of a Blob.

    `.Blob` objects can represent their data in various ways. Each of
    those options must provide three ways to access the data, which are the
    `content` property, the `save()` method, and the `open()` method.

    This base class defines the interface needed by any data store used by a
    `.Blob`.

    Blobs that store their data locally should subclass `.LocalBlobData`
    which adds a `response()` method and `id` property, appropriate for data
    that would need to be downloaded from a server. It also takes care of
    generating a download URL when it's needed.
    """

    def __init__(self, media_type: str) -> None:
        """Initialise a `.BlobData` object.

        :param media_type: the MIME type of the data.
        """
        self._media_type = media_type

    @property
    def media_type(self) -> str:
        """The MIME type of the data, e.g. 'image/png' or 'application/json'."""
        return self._media_type

    def get_href(self) -> str:
        """Return the URL to download the blob.

        The implementation of this method for local blobs will need
        `.url_for.url_for` and thus it should only be called in a response
        handler when the `.middeware.url_for` middleware is enabled.
        """
        raise NotImplementedError("get_href must be implemented.")

    @property
    def content(self) -> bytes:
        """The data as a `bytes` object.

        :raises NotImplementedError: always, as this must be implemented by subclasses.
        """
        raise NotImplementedError("content property must be implemented.")

    def save(self, filename: str) -> None:
        """Save the data to a file.

        :param filename: the path where the file should be saved.
        """
        raise NotImplementedError("save must be implemented.")

    def open(self) -> io.IOBase:
        """Return a file-like object that may be read from.

        :return: an open file-like object.
        """
        raise NotImplementedError("open must be implemented.")


class RemoteBlobData(BlobData):
    r"""A BlobData subclass that references remote data via a URL.

    This `.BlobData` implementation will download data lazily, and
    provides it in the three ways defined by `.BlobData`\ . It
    does not cache downloaded data: if the `.content` attribute is
    accessed multiple times, the data will be downloaded again each
    time.

    .. note::

        This class is rarely instantiated directly. It is usually best to use
        `.Blob.from_url` on a `.Blob` subclass.
    """

    def __init__(
        self, media_type: str, href: str, client: httpx.Client | None = None
    ) -> None:
        """Create a reference to remote `.Blob` data.

        :param media_type: the MIME type of the data.
        :param href: the URL where it may be downloaded.
        :param client: if supplied, this `httpx.Client` will be used to
            download the data.
        """
        super().__init__(media_type=media_type)
        self._href = href
        self._client = client or httpx.Client()

    def get_href(self) -> str:
        """Return the URL to download the data."""
        return self._href

    @property
    def content(self) -> bytes:
        """The binary data, as a `bytes` object."""
        return self._client.get(self._href).content

    def save(self, filepath: str) -> None:
        """Save the output to a file.

        Note that the current implementation retrieves the data into
        memory in its entirety, and saves to file afterwards.

        :param filepath: the file will be saved at this location.
        """
        with open(filepath, "wb") as f:
            f.write(self.content)

    def open(self) -> io.IOBase:
        """Open the output as a binary file-like object.

        Internally, this will download the file to memory, and wrap the
        resulting `bytes` object in an `io.BytesIO` object to allow it to
        function as a file-like object.

        To work with the data on disk, use `save` instead.

        :return: a file-like object containing the downloaded data.
        """
        return io.BytesIO(self.content)


class LocalBlobData(BlobData):
    """A BlobData subclass where the data is stored locally.

    `.Blob` objects can reference data by a URL, or can wrap data
    held in memory or on disk. For the non-URL options, we need to register the
    data with the `.BlobManager` and allow it to be downloaded. This class takes
    care of registering with the `.BlobManager` and adds the `.response` method
    that must be overridden by subclasses to allow downloading.

    See `.BlobBytes` or `.BlobFile` for concrete implementations.
    """

    def __init__(self, media_type: str) -> None:
        """Initialise the LocalBlobData object.

        :param media_type: the MIME type of the data.
        """
        super().__init__(media_type=media_type)
        self._id = blob_data_manager.add_blob(self)

    @property
    def id(self) -> uuid.UUID:
        """A unique identifier for this BlobData object.

        The ID is set when the BlobData object is added to the `BlobDataManager`
        during initialisation.
        """
        return self._id

    def get_href(self) -> str:
        r"""Return a URL where this data may be downloaded.

        Note that this should only be called in a response handler, as it
        relies on `.url_for.url_for`\ .
        """
        return str(url_for("download_blob", blob_id=self.id))

    def response(self) -> Response:
        """Return a`fastapi.Response` object that sends binary data.

        :return: a response that streams the data from disk or memory.
        """
        raise NotImplementedError


class BlobBytes(LocalBlobData):
    """A `.Blob` that holds its data in memory as a `bytes` object.

    `.Blob` objects use objects conforming to the `.BlobData` protocol to
    store their data either on disk or in a file. This implements the protocol
    using a `bytes` object in memory.

    .. note::

        This class is rarely instantiated directly. It is usually best to use
        `.Blob.from_bytes` on a `.Blob` subclass.
    """

    _id: uuid.UUID

    def __init__(self, data: bytes, media_type: str) -> None:
        """Create a `.BlobBytes` object.

        .. note::

            This class is rarely instantiated directly. It is usually best to use
            `.Blob.from_bytes` on a `.Blob` subclass.

        :param data: is the data to be wrapped.
        :param media_type: is the MIME type of the data.
        """
        super().__init__(media_type=media_type)
        self._bytes = data

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


class BlobFile(LocalBlobData):
    """A `.BlobData` backed by a file on disk.

    Only the filepath is retained by default. If you are using e.g. a temporary
    directory, you should add the `.TemporaryDirectory` as an instance attribute,
    to stop it being garbage collected. See `.Blob.from_temporary_directory`.

    .. note::

        This class is rarely instantiated directly. It is usually best to use
        `.Blob.from_file` on a `.Blob` subclass.
    """

    def __init__(self, file_path: str, media_type: str, **kwargs: Any) -> None:
        r"""Create a `.BlobFile` to wrap data stored on disk.

        `.BlobFile` objects wrap data stored on disk as files. They
        are not usually instantiated directly, but made using
        `.Blob.from_temporary_directory` or `.Blob.from_file`.

        :param file_path: is the path to the file.
        :param media_type: is the MIME type of the data.
        :param \**kwargs: will be added to the object as instance
            attributes. This may be used to stop temporary directories
            from being garbage collected while the `.Blob` exists.

        :raise IOError: if the file specified does not exist.
        """
        super().__init__(media_type=media_type)
        if not os.path.exists(file_path):
            raise IOError("Tried to return a file that doesn't exist.")
        self._file_path = file_path
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


class BlobModel(BaseModel):
    """A model for JSON-serialised `.Blob` objects.

    This model describes the JSON representation of a `.Blob`
    and does not offer any useful functionality.
    """

    href: str
    """The URL where the data may be retrieved."""
    media_type: str
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


class Blob:
    r"""A container for binary data that may be retrieved over HTTP.

    See :ref:`blobs` for more information on how to use this class.

    A `.Blob` may be created to hold data using the class methods
    `.Blob.from_bytes`, `.Blob.from_file` or `.Blob.from_temporary_directory`\ .
    It may also reference remote data, using `.Blob.from_url`\ .
    The constructor requires a `.BlobData` instance, so the methods mentioned
    previously are likely more convenient.

    You are strongly advised to use a subclass of this class that specifies the
    `.Blob.media_type` attribute, as this will propagate to the auto-generated
    documentation.

    This class is `pydantic` compatible, in that it provides a schema, validator
    and serialiser. However, it may use `.url_for.url_for` during serialisation,
    so it should only be serialised in a request handler function. This
    functionality is intended for use by LabThings library functions only.
    """

    media_type: str = "*/*"
    """The MIME type of the data. This should be overridden in subclasses."""
    description: str | None = None
    """An optional description that may be added to the serialised `.Blob`."""
    _data: BlobData
    """This object stores the data - in memory, on disk, or at a URL."""

    def __init__(self, data: BlobData, description: str | None = None) -> None:
        """Create a `.Blob` object wrapping the given data.

        :param data: the `.BlobData` object that stores the data.
        :param description: an optional description of the blob.
        """
        super().__init__()
        self._data = data
        if description is not None:
            self.description = description

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[Any], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """Get the pydantic core schema for this type.

        This magic method allows `pydantic` to serialise `.Blob`
        instances, and generate a JSONSchema for them.

        The representation of a `.Blob` in JSON is described by
        `.BlobModel` and includes the ``href`` and ``media_type`` properties
        as well as a description.

        When a `.Blob` is serialised, we will generate a download URL that
        matches the request to which we are responding. This means we may
        only serialise a `.Blob` in the context of a request handler, and
        it's required that the `.middleware.url_for` middleware is in use.

        When a `.Blob` is validated, we will check to see if the URL given
        as its ``href`` looks like a `.Blob` download URL on this server. If
        it does, the returned object will hold a reference to the local data.
        If we can't match the URL to a `.Blob` on this server, we will raise
        an error. Handling of `.Blob` input is currently experimental, and
        limited to passing the output of one Action as input to a subsequent
        one.

        :param source: The source type being converted.
        :param handler: The pydantic core schema handler.
        :return: The pydantic core schema for the URLFor type.
        """
        return core_schema.no_info_wrap_validator_function(
            cls._validate,
            BlobModel.__get_pydantic_core_schema__(BlobModel, handler),
            serialization=core_schema.wrap_serializer_function_ser_schema(
                cls._serialize,
                is_field_serializer=False,
                info_arg=False,
                when_used="always",
            ),
        )

    @classmethod
    def _validate(cls, value: Any, handler: Callable[[Any], BlobModel]) -> Self:
        r"""Validate and convert a value to a `.Blob` instance.

        :param value: The value to validate.
        :param handler: The handler to convert the value if needed.

        When a `.Blob` is created from a dictionary, LabThings
        will attempt to deserialise it by retrieving the data from the URL
        specified in `.Blob.href`. Currently, this must be a URL pointing to a
        `.Blob` that already exists on this server, and any other URL will
        cause a `LookupError`.

        :return: the `.Blob` object (i.e. ``self``), after retrieving the data.

        :raise ValueError: if the ``href`` is set as ``"blob://local"`` but
            the ``_data`` attribute has not been set. This happens when the
            `.Blob` is being constructed using `.Blob.from_bytes` or similar.
        """
        # If the value is already a Blob, return it directly
        if isinstance(value, cls):
            return value
        # We start by validating the input, which should fit a `BlobModel`
        # (this validator is wrapping the BlobModel schema)
        model = handler(value)
        id = url_to_id(model.href)
        if not id:
            raise ValueError("Blob URLs must contain a Blob ID.")
        try:
            data = blob_data_manager.get_blob(id)
            return cls(data)
        except KeyError as error:
            raise ValueError(f"Blob ID {id} wasn't found on this server.") from error

    @classmethod
    def _serialize(
        cls, obj: Self, handler: Callable[[BlobModel], Mapping[str, str]]
    ) -> Mapping[str, str]:
        """Serialise the Blob to a dictionary.

        :param obj: the `.Blob` instance to serialise.
        :return: a JSON-serialisable dictionary with a URL that allows
            the `.Blob` to be downloaded from the `.BlobManager`.
        """
        return handler(obj.to_blobmodel())

    def to_blobmodel(self) -> BlobModel:
        r"""Represent the `.Blob` as a `.BlobModel` to get ready to serialise.

        When `pydantic` serialises this object, we first generate a `.BlobModel`
        witht just the information to be serialised.
        We use `.from_url.from_url` to generate the URL, so this will error if
        it is serialised anywhere other than a request handler with the
        middleware from `.middleware.url_for` enabled.

        :return: a JSON-serialisable dictionary with a URL that allows
            the `.Blob` to be downloaded from the `.BlobManager`.
        :raises TypeError: if the blob data ID is missing. This should
            never happen, and if it does it's probably a bug in the
            `.BlobData` class.
        """
        data = {
            "href": self.data.get_href(),
            "media_type": self.media_type,
        }
        if self.description is not None:
            data["description"] = self.description
        return BlobModel(**data)

    @property
    def data(self) -> BlobData:
        """The data store for this Blob.

        It is recommended to use the `.Blob.content` property or `.Blob.save`
        or `.Blob.open`
        methods rather than accessing this property directly.

        :return: the data store wrapping data on disk or in memory.
        """
        return self._data

    @property
    def content(self) -> bytes:
        """Return the the output as a `bytes` object.

        This property may return the `bytes` object, or if we have a file it
        will read the file and return the contents. Client objects may use
        this property to download the output.

        This property is read-only. You should also only read it once, as no
        guarantees are given about caching - reading it many times risks
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
        return cls(BlobBytes(data, media_type=cls.media_type))

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
        return cls(
            BlobFile(
                file_path,
                media_type=cls.media_type,
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
        return cls(
            BlobFile(file, media_type=cls.media_type),
        )

    @classmethod
    def from_url(cls, href: str, client: httpx.Client | None = None) -> Self:
        """Create a `.Blob` that references data at a URL.

        This is the recommended way to create a `.Blob` that references
        data held remotely. It should ideally be called on a subclass
        of `.Blob` that has set ``media_type``.

        :param href: the URL where the data may be downloaded.
        :param client: if supplied, this `httpx.Client` will be used to
            download the data.

        :return: a `.Blob` object referencing the specified URL.
        """
        return cls(
            RemoteBlobData(
                media_type=cls.media_type,
                href=href,
                client=client,
            ),
        )

    def response(self) -> Response:
        """Return a suitable response for serving the output.

        This method is called by the `.ThingServer` to generate a response
        that returns the data over HTTP.

        :return: an HTTP response that streams data from memory or file.
        """
        data = self.data
        if isinstance(data, LocalBlobData):
            return data.response()
        else:
            raise NotImplementedError(
                "Currently, only local BlobData can be served over HTTP."
            )


def blob_type(media_type: str) -> type[Blob]:
    r"""Create a `.Blob` subclass for a given media type.

    This convenience function may confuse static type checkers, so it is usually
    clearer to make a subclass instead, e.g.:

    .. code-block:: python

        class MyImageBlob(Blob):
            media_type = "image/png"

    :param media_type: the media type that the new `.Blob` subclass will use.

    :return: a subclass of `.Blob` with the specified media type.

    :raise ValueError: if the media type contains ``'`` or ``\``.
    """
    warn(
        "`blob_type` is deprecated and will be removed in v0.1.0. "
        "Create a subclass of `Blob` instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    if "'" in media_type or "\\" in media_type:
        raise ValueError("media_type must not contain single quotes or backslashes")
    return type(
        f"{media_type.replace('/', '_')}_blob",
        (Blob,),
        {
            "media_type": media_type,
        },
    )


class BlobDataManager:
    r"""A class to manage BlobData objects.

    The `.BlobManager` is responsible for serving `.Blob` objects to clients. It
    holds weak references: it will not retain `.Blob`\ s that are no longer in use.
    Most `.Blob`\ s will be retained by the output of an action: this holds a strong
    reference, and will be expired by the `.ActionManager`.

    Note that the `.BlobDataManager` does not work with `.Blob` objects directly,
    it holds only the `.LocalBlobData` object, which is where the data is
    stored. This means you should not rely on any custom attributes of a `.Blob`
    subclass being preserved when the `.Blob` is passed from one action to another.

    See :ref:`blobs` for an overview of how `.Blob` objects should be used.
    """

    def __init__(self) -> None:
        """Initialise a BlobDataManager object."""
        self._blobs: WeakValueDictionary[uuid.UUID, LocalBlobData] = (
            WeakValueDictionary()
        )

    def add_blob(self, blob: LocalBlobData) -> uuid.UUID:
        """Add a `.Blob` to the manager, generating a unique ID.

        This function adds a `.LocalBlobData` object to the
        `.BlobDataManager`. It will retain a weak reference to the
        `.LocalBlobData` object: you are responsible for ensuring
        the data is not garbage collected, for example by including the
        parent `.Blob` in the output of an action.

        :param blob: a `.LocalBlobData` object that holds the data
            being added.

        :return: a unique ID identifying the data. This forms part of
            the URL to download the data.

        :raise ValueError: if the `.LocalBlobData` object already
            has an ``id`` attribute but is not in the dictionary of
            data. This suggests the object has been added to another
            `.BlobDataManager`, which should never happen.
        """
        if blob in self._blobs.values():
            raise ValueError(
                "BlobData objects may only be added to the manager once! "
                "This is a LabThings bug."
            )
        id = uuid.uuid4()
        self._blobs[id] = blob
        return id

    def get_blob(self, blob_id: uuid.UUID) -> LocalBlobData:
        """Retrieve a `.Blob` from the manager.

        :param blob_id: the unique ID assigned when the data was added to
            this `.BlobDataManager`.

        :return: the `.LocalBlobData` object holding the data.
        """
        return self._blobs[blob_id]

    def download_blob(self, blob_id: uuid.UUID) -> Response:
        """Download a `.Blob`.

        This function returns a `fastapi.Response` allowing the data to be
        downloaded, using the `.LocalBlobData.response` method.

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
        the `.LocalBlobData` objects in response to ``GET`` requests.

        :param app: the `fastapi.FastAPI` application to which we are adding
            the endpoint.
        """
        app.get(
            "/blob/{blob_id}",
            name="download_blob",
        )(self.download_blob)


blob_data_manager = BlobDataManager()
"""A global register of all BlobData objects."""


def url_to_id(url: str) -> uuid.UUID | None:
    """Extract the blob ID from a URL.

    Currently, this checks for a UUID at the end of a URL. In the future,
    it might check if the URL refers to this server.

    :param url: a URL previously generated by `blobdata_to_url`.
    :return: the UUID blob ID extracted from the URL.
    """
    m = re.search(r"blob/([0-9a-z\-]+)", url)
    if not m:
        return None
    return uuid.UUID(m.group(1))
