"""Basic support for numpy arrays in Pydantic models.

We define a type alias `.NDArray` which is a numpy array, annotated
to allow `pydantic` to convert it to and from JSON (as an array-of-arrays).

This should allow numpy arrays to be used without explicit conversion:

.. code-block:: python

    from labthings_fastapi.types.ndarray import NDArray


    def double(arr: NDArray) -> NDArray:
        return arr * 2  # arr is a numpy.ndarray

The implementation is not super elegant: it isn't recursive so has only been
defined for up to 6d arrays. Specifying the dimensionality might be a nice
touch, but is left for the future.

Complex numbers are currently not supported, again this is left for the future.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Annotated, Any, List, Literal, Self, Union, cast

import numpy as np
from pydantic import (
    Base64Bytes,
    BaseModel,
    ConfigDict,
    GetCoreSchemaHandler,
    PlainSerializer,
    PlainValidator,
    RootModel,
    SerializerFunctionWrapHandler,
    WithJsonSchema,
    WrapSerializer,
)
from pydantic_core import core_schema
from typing_extensions import TypeAlias

# Define a nested list of floats with 0-6 dimensions
# This would be most elegantly defined as a recursive type
# but the below gets the job done for now.
Number: TypeAlias = Union[int, float]
NestedListOfNumbers: TypeAlias = Union[
    Number,
    List[Number],
    List[List[Number]],
    List[List[List[Number]]],
    List[List[List[List[Number]]]],
    List[List[List[List[List[Number]]]]],
    List[List[List[List[List[List[Number]]]]]],
    List[List[List[List[List[List[List]]]]]],
]


class NestedListOfNumbersModel(RootModel):
    """A RootModel describing a list-of-lists up to 7 deep.

    This is used to generate a JSONSchema description of a `numpy.ndarray`
    serialised to a list. It is used in the annotated `.NDArray` type.
    """

    root: NestedListOfNumbers


def np_to_listoflists(arr: np.ndarray) -> NestedListOfNumbers:
    """Convert a numpy array to a list of lists.

    NB this will not be quick! Large arrays will be much better
    serialised by dumping to base64 encoding or similar.

    :param arr: a `numpy.ndarray`.
    :return: a nested list of numbers.
    """
    return arr.tolist()


def listoflists_to_np(lol: Union[NestedListOfNumbers, np.ndarray]) -> np.ndarray:
    """Convert a list of lists to a numpy array (or pass-through ndarrays).

    :param lol: a nested list of numbers.
    :return: a `numpy.ndarray`.
    """
    return np.asarray(lol)


# Define an annotated type so Pydantic can cope with numpy
NDArray: TypeAlias = Annotated[
    np.ndarray,
    PlainValidator(listoflists_to_np),
    PlainSerializer(
        np_to_listoflists, when_used="json-unless-none", return_type=NestedListOfNumbers
    ),
    WithJsonSchema(NestedListOfNumbersModel.model_json_schema(), mode="validation"),
]
r"""An annotated type that enables `pydantic` to handle `numpy.ndarray`\ .

`.NDArray` "validates" `numpy.ndarray` objects by converting a nested list of
numbers into an `numpy.ndarray` using `numpy.asarray`\ . Similarly, it calls
`numpy.ndarray.tolist` to convert the array back into a serialisable structure.

The JSON Schema representation is a nested list up to 7 deep, which is cumbersome
but correct.

In the future it would be good to replace this type with several types of
different, specified dimensionality. That would make for much less horrible
:ref:`wot_td` representations, as well as giving useful information about the datatype
returned.
"""


def denumpify(v: Any) -> Any:
    """Convert any numpy array in a dict into a list.

    :param v: the data to convert, may be a mapping, sequence, or other.

    :return: the input datastructure, with all `numpy.ndarray` objects
        converted to lists.
    """
    if isinstance(v, np.ndarray):
        return v.tolist()
    elif isinstance(v, Mapping):
        return {k: denumpify(vv) for k, vv in v.items()}
    elif isinstance(v, Sequence):
        return [denumpify(vv) for vv in v]
    else:
        return v


def denumpify_serialiser(v: Any, nxt: SerializerFunctionWrapHandler) -> Any:
    """Denumpify mappings before serialization.

    This is intended for use as a "wrap serialiser" in `pydantic`, and
    will remove `numpy.ndarray` objects from a data structure using
    `.denumpify`. This should allow dicts containing `numpy.ndarray`
    objects to be serialised to JSON.

    :param v: input data, of any type.
    :param nxt: the next serialiser, see `pydantic` docs.

    :return: the data structure with `numpy.ndarray` objects removed.
    """
    return nxt(denumpify(v))


class DenumpifyingDict(RootModel):
    """A `pydantic` model for a dictionary that converts arrays to lists."""

    root: Annotated[Mapping, WrapSerializer(denumpify_serialiser)]
    model_config = ConfigDict(arbitrary_types_allowed=True)


ElementType: TypeAlias = Literal["bool", "uint", "int", "float", "complex"]


ELEMENT_TYPES_BY_KIND: dict[str, ElementType] = {
    "b": "bool",
    "u": "uint",
    "i": "int",
    "f": "float",
    "c": "complex",
}
"""A mapping from numpy ``dtype.kind`` to element type names.

The single-letter codes are documented at `numpy.dtype.kind` but are
specific to `numpy`. LabThings uses slightly more verbose notation
that ought to be clear to someone working in any language.
"""


KINDS_BY_ELEMENT_TYPE = {etype: kind for kind, etype in ELEMENT_TYPES_BY_KIND.items()}
"""A mapping from element type names to `numpy.dtype.kind` values."""


def byte_order_name(native: bool) -> Literal["little", "big"]:
    """Return the name for a byte order.

    :param native: whether to return the machine's byte order.
    :return: the machine's byte order, or the other order, as a string.
    """
    if native:
        return sys.byteorder
    else:
        return "little" if sys.byteorder == "big" else "big"


class Base64NDArrayModel(BaseModel):
    """A Pydantic model for numpy arrays."""

    element_type: ElementType
    """The datatype of each array element."""

    element_length: int
    """The length of each array element in bytes."""

    byte_order: Literal["little", "big"]
    """Whether the data is in little-endian or big-endian format."""

    shape: tuple[int, ...]
    """The shape of the array, i.e. the length in each dimension."""

    array_order: Literal["c-contiguous"]
    """Whether the array elements are in C or fortran order.

    Currently only c order is supported.
    """

    data: Base64Bytes
    """The data for the array, Base64 encoded."""

    @property
    def _kind(self) -> str:
        """A one-character string describing the element_type."""
        return KINDS_BY_ELEMENT_TYPE[self.element_type]

    @property
    def _endian_char(self) -> str:
        """A one-character string describing endianness."""
        if self.element_length == 1:
            return "|"  # one-byte values have no endianness
        return "<" if self.byte_order == "little" else ">"

    @property
    def _descr(self) -> list[tuple[str, str]]:
        """The expected value of `numpy.dtype.descr` for this array.

        This property may be compared with `array.dtype.descr` and ought
        to match exactly. If it doesn't, we have found an edge case.
        """
        return [("", f"{self._endian_char}{self._kind}{self.element_length}")]

    @classmethod
    def from_array(cls, array: np.ndarray) -> Self:
        """Construct a Base64NDArrayModel from a numpy array.

        Note that this will raise an exception if the array is not in a supported
        format. This class only deals with boolean or numeric arrays.

        :param array: a `numpy.ndarray` object.
        :return: a validated model holding the array's data.
        :raises ValueError: if the array has an unsupported type.
        """
        dtype = array.dtype
        if dtype.kind not in ELEMENT_TYPES_BY_KIND:
            raise ValueError(f"The array has dtype '{dtype}' which is not supported.")
        _model = cls.model_construct(
            element_type=ELEMENT_TYPES_BY_KIND[dtype.kind],
            element_length=dtype.itemsize,
            byte_order=byte_order_name(dtype.isnative),
            shape=array.shape,
            array_order="c-contiguous",
            data=array.tobytes(order="C"),
        )
        # This comment block explains the cast statement below.
        # _model will have type Self, because that's the type of `cls.model_construct`.
        # MyPy infers the type as Base64ArrayModel rather than Self, which is correct
        # in the base class but is incorrect for a subclass. The cast below types it
        # correctly. For `Base64ArrayModel` this is a no-op, as `Self` refers to the
        # same type. In a subclass, this could potentially be helpful.
        # FWIW `BaseModel.model_construct` is correctly typed as returning
        # Self so this feels like a MyPy/Pydantic interaction problem.
        model = cast(Self, _model)
        if model._descr != dtype.descr:
            raise ValueError(
                "The array dtype couldn't be matched. "
                f"Input dtype.descr='{dtype.descr}', Expected '{model._descr}'."
            )
        return model

    def to_array(self) -> np.ndarray:
        """Construct a numpy array from this model.

        :return: the data, reinflated to a `numpy.ndarray` object.
        """
        dtype = np.dtype(f"{self._endian_char}{self._kind}{self.element_length}")
        return np.frombuffer(self.data, dtype=dtype).reshape(self.shape)


class NDArrayAnnotation:
    """A class that enables serialisation and validation of `numpy` arrays.

    This class is intended to be used as part of an annotated type, i.e.
    ``Annotated[np.ndarray, NDArrayAnnotation]``.

    For documentation on how this works, see the relevant section of the
    `pydantic` docs:

    https://pydantic.dev/docs/validation/dev/concepts/types/#as-an-annotation
    """

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[Any], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """Get the pydantic core schema for this type.

        This magic method allows `pydantic` to serialise `.Blob`
        instances, and generate a JSONSchema for them.

        We tell `pydantic` to base its handling of `Blob` on the
        `.BlobModel` schema, with custom validation and serialisation.
        Validation and serialisation behaviour is described in the docstrings
        of `.Blob._validate` and `.Blob._serialise`.

        The JSONSchema is generated for `.BlobModel` but is then refined
        in `__get_pydantic_json_schema__` to include the ``media_type``
        and ``description`` defaults.

        :param source: The source type being converted.
        :param handler: The pydantic core schema handler.
        :return: The pydantic core schema for the URLFor type.
        """
        return core_schema.no_info_wrap_validator_function(
            cls._validate,
            Base64NDArrayModel.__pydantic_core_schema__,
            serialization=core_schema.wrap_serializer_function_ser_schema(
                cls._serialise,
                is_field_serializer=False,
                info_arg=False,
                when_used="always",
            ),
        )

    # @classmethod
    # def __get_pydantic_json_schema__(
    #     cls, core_schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    # ) -> JsonSchemaValue:
    #     """Customise the JSON Schema to include the media_type.

    #     :param core_schema: The core schema.
    #     :param handler: The pydantic JSON schema handler.
    #     :return: The JSON schema for the type, with media_type included.
    #     """
    #     json_schema = handler(core_schema)
    #     json_schema = handler.resolve_ref_schema(json_schema)
    #     # Set the title to the class name, not BlobModel
    #     json_schema["title"] = "Numeric Array"
    #     return json_schema

    @classmethod
    def _validate(
        cls, value: Any, handler: Callable[[Any], Base64NDArrayModel]
    ) -> np.ndarray:
        r"""Validate and convert a value to a `numpy.ndarray` instance.

        :param value: The input value, as passed in or loaded from JSON.
        :param handler: A function that runs the validation logic of Base64NDArrayModel.

        If the value is already a `~numpy.ndarray`, it will be returned directly.
        Otherwise, we first validate the input using the `Base64NDArrayModel` schema.

        :return: a `~numpy.ndarray` object.
        """
        # If the value is already a Blob, return it directly
        if isinstance(value, np.ndarray):
            return value
        # If not, validate it using the array model
        model = handler(value)
        return model.to_array()

    @classmethod
    def _serialise(
        cls, obj: np.ndarray, handler: Callable[[Base64NDArrayModel], Mapping[str, str]]
    ) -> Mapping[str, str]:
        """Serialise the Blob to a dictionary.

        See `.Blob.to_blobmodel` for a description of how we serialise.

        :param obj: the `.Blob` instance to serialise.
        :param handler: the handler (provided by pydantic) takes a BlobModel
            and converts it to a dictionary. The handler runs the serialiser of
            the core schema we've wrapped, in this case the BlobModel serialiser.
        :return: a JSON-serialisable dictionary with a URL that allows
            the `.Blob` to be downloaded from the `.BlobManager`.
        """
        return handler(Base64NDArrayModel.from_array(obj))
