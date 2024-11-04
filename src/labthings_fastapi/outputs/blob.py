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
import re
import shutil
from typing import (
    Annotated,
    Any,
    Literal,
    Mapping,
    Optional,
    TypeAlias,
    Union,
    TYPE_CHECKING,
)
from tempfile import TemporaryDirectory
import uuid

from fastapi.responses import FileResponse, Response
from pydantic import (
    BaseModel,
    PlainSerializer,
    PlainValidator,
    WithJsonSchema,
    create_model,
)
from pydantic_core import PydanticUndefined
from starlette.exceptions import HTTPException
from typing_extensions import Self, Protocol, runtime_checkable

if TYPE_CHECKING:
    from labthings_fastapi.actions import ActionManager


@runtime_checkable
class BlobOutputProtocol(Protocol):
    """A Protocol for a BlobOutput object"""

    @property
    def media_type(self) -> str:
        pass

    @property
    def content(self) -> bytes:
        pass

    def save(self, filename: str) -> None: ...

    def open(self) -> io.IOBase: ...


class ServerSideBlobOutputProtocol(BlobOutputProtocol, Protocol):
    """A BlobOutput protocol for server-side use, i.e. including `response()`"""

    def response(self) -> Response: ...


def is_blob_output(obj: Any) -> bool:
    """Check if a class is a BlobOutput"""
    # We do this based on the protocol - but because I've used properties in the protocol,
    # I can't just use issubclass.
    for attr in ServerSideBlobOutputProtocol.__protocol_attrs__:  # type: ignore[attr-defined]
        if not hasattr(obj, attr):
            return False
    return True


class BlobOutputModel(BaseModel):
    """A Pydantic model describing a BlobOutput"""

    media_type: str
    href: str
    rel: Literal["output"] = "output"
    description: str = (
        "The output from this action is not serialised to JSON, so it must be "
        "retrieved as a file. This link will return the file."
    )


def get_model_media_type(model: type) -> Optional[str]:
    """Return the media type of a BlobOutput model"""
    if is_blob_output(model):
        return model.media_type  # type: ignore[attr-defined] # (checked for in is_blob_output)
    try:
        media_type = model.model_fields["media_type"].default  # type: ignore[attr-defined]
        if media_type is PydanticUndefined:
            return None
        return media_type
    except KeyError:  # If there's no media_type field, ignore it
        pass
    except AttributeError:  # If it's not a Pydantic model, ignore it
        pass
    return None


def blob_output_model(media_type: str) -> type[BlobOutputModel]:
    """Create a BlobOutput subclass for a given media type"""
    if "'" in media_type or "\\" in media_type:
        raise ValueError("media_type must not contain single quotes or backslashes")
    return create_model(
        f"blob_output_{media_type.replace('/', '_')}",
        __base__=BlobOutputModel,
        media_type=(eval(f"Literal[r'{media_type}']"), media_type),
    )


def blob_to_model(output_type: type) -> type:
    """Substitute BlobOutputModel for BlobOutput subclasses

    This function converts BlobOutput classes to a Pydantic model, so
    that the output is a JSON object containing the media type and a link.
    NB this uses "duck typing", so the class need only expose the necessary
    attributes.

    NB this *only* converts the `output_model` of an `ActionDescriptor`, it
    does not automatically process the actual output of the function.
    """
    if is_blob_output(output_type):
        return blob_output_model(output_type.media_type)  # type: ignore[attr-defined]
    return output_type


def blob_to_link(output: Any, output_href: str) -> Any:
    """If the argument is a BlobOutput, convert it to a link.

    Actions that return BlobOutput subclasses can't embed their output in a
    JSON response, so we convert them to a link. This function does that.
    Following the link will download the output as a file. We return a
    dictionary rather than a BlobOutput object so that the output model
    is used (which checks the media type for us).

    NB this uses "duck typing" so may become stricter in the future.
    """
    if is_blob_output(output):
        return {
            "media_type": output.media_type,
            "href": output_href,
        }
    return output


def blob_to_dict(blob: BlobOutput) -> Mapping[str, str]:
    """Convert a BlobOutput to a dictionary

    This function is used to convert a BlobOutput object to a dictionary, so that
    it can be serialised to JSON. It currently only serialises outputs of actions
    correctly, and relies on a context variable being set, usually with a dependency.
    """
    return {"error": "BlobOutput objects should not be serialised yet"}


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

    def save(self, filepath: str) -> None:
        """Save the output to a file.

        This may remove the need to hold the output in memory.
        """
        if hasattr(self, "_bytes"):
            with open(filepath, "wb") as f:
                f.write(self._bytes)
        elif hasattr(self, "_file_path"):
            shutil.copyfile(self._file_path, filepath)
        else:
            raise NEITHER_BYTES_NOR_FILE

    def open(self) -> io.IOBase:
        """Open the output as a binary file-like object."""
        if hasattr(self, "_bytes"):
            return io.BytesIO(self._bytes)
        if hasattr(self, "_file_path"):
            return open(self._file_path, mode="rb")
        raise NEITHER_BYTES_NOR_FILE

    @classmethod
    def from_bytes(cls, data: bytes) -> Self:
        """Create a BlobOutput from a bytes object"""
        obj = cls()
        obj._bytes = data
        return obj

    @classmethod
    def from_temporary_directory(cls, folder: TemporaryDirectory, file: str) -> Self:
        """Create a BlobOutput from a file in a temporary directory

        The TemporaryDirectory object will persist as long as this BlobOutput does,
        which will prevent it from being cleaned up until the object is garbage
        collected.
        """
        obj = cls()
        obj._file_path = os.path.join(folder.name, file)
        obj._temporary_directory = folder
        return obj

    @classmethod
    def from_file(cls, file: str) -> Self:
        """Create a BlobOutput from a regular file

        The file should exist for at least as long as the BlobOutput does; this
        is assumed to be the case and nothing is done to ensure it's not
        temporary. If you are using temporary files, consider creating your
        BlobOutput with `from_temporary_directory` instead.
        """
        if not os.path.exists(file):
            raise IOError("Tried to return a file that doesn't exist.")
        obj = cls()
        obj._file_path = file
        return obj

    def response(self):
        """ "Return a suitable response for serving the output"""
        if hasattr(self, "_bytes"):
            return Response(content=self._bytes, media_type=self.media_type)
        if hasattr(self, "_file_path"):
            return FileResponse(self._file_path, media_type=self.media_type)
        raise NEITHER_BYTES_NOR_FILE


def retrieve_blob_output(
    blob_model: BlobOutputModel, action_manager: ActionManager
) -> BlobOutput:
    """Retrieve a BlobOutput from a BlobOutputModel

    This function is intended to be used by the server to retrieve a BlobOutput
    object from a BlobOutputModel. It will use the `href` field to retrieve the
    output from the action manager, and return a BlobOutput object.
    """
    if blob_model.rel != "output":
        raise ValueError("Currently, blobs must be action outputs.")
    print(f"Retrieving invocation ID from string {blob_model.href}")
    m = re.search(r"action_invocations/([0-9a-z\-]+)/output", blob_model.href)
    try:
        if not m:
            raise HTTPException(
                status_code=404, detail="Could not find invocation ID in href"
            )
        invocation_id = uuid.UUID(m.group(1))
        output = action_manager.get_invocation(invocation_id).output
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Invocation {invocation_id} not found"
        )
    assert isinstance(output, BlobOutput)
    assert output.media_type == blob_model.media_type
    return output


def ensure_blob_output(obj: Union[BlobOutput, BlobOutputModel, Mapping]) -> BlobOutput:
    """Convert a BlobOutputModel or dict to a BlobOutput

    This function is used as a `pydantic` validator. `BlobOutput` objects are
    passed through unchanged, `BlobOutputModel` objects are converted to a
    `BlobOutput` object, and dictionaries are converted to a `BlobOutput` object
    via a `BlobOutputModel`.
    """
    if isinstance(obj, BlobOutput):
        return obj
    from labthings_fastapi.dependencies.action_manager import ActionManagerContext

    if isinstance(obj, BlobOutputModel):
        return retrieve_blob_output(obj, ActionManagerContext.get())
    if isinstance(obj, Mapping):
        return retrieve_blob_output(BlobOutputModel(**obj), ActionManagerContext.get())
    raise ValueError("Object is not a BlobOutput or BlobOutputModel")


Blob: TypeAlias = Annotated[
    BlobOutput,
    PlainValidator(ensure_blob_output),
    PlainSerializer(blob_to_link, when_used="json-unless-none"),
    WithJsonSchema(BlobOutputModel.model_json_schema(), mode="validation"),
]


def blob_type(media_type: str) -> type[BlobOutput]:
    """Create a BlobOutput subclass for a given media type"""
    my_media_type = media_type  # Ensure media type is remembered in a closure,

    # for the class definition below
    class BlobOutputSubclass(BlobOutput):
        media_type = my_media_type

    model = blob_output_model(media_type)
    return Annotated[  # type: ignore[return-value]
        BlobOutputSubclass,
        PlainValidator(ensure_blob_output),
        PlainSerializer(blob_to_dict, when_used="json-unless-none"),
        WithJsonSchema(model.model_json_schema(), mode="validation"),
    ]
