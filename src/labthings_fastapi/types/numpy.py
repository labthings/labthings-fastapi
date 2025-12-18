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
import numpy as np
from pydantic import (
    ConfigDict,
    PlainSerializer,
    PlainValidator,
    RootModel,
    SerializerFunctionWrapHandler,
    WithJsonSchema,
    WrapSerializer,
)
from typing import Annotated, Any, List, Union
from typing_extensions import TypeAlias
from collections.abc import Mapping, Sequence


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


def denumpify_serializer(v: Any, nxt: SerializerFunctionWrapHandler) -> Any:
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

    root: Annotated[Mapping, WrapSerializer(denumpify_serializer)]
    model_config = ConfigDict(arbitrary_types_allowed=True)


class ArrayModel(RootModel):
    """A model automatically used by actions as the return type for a numpy array.

    This models is passed to FastAPI as the return model for any action that returns
    a numpy array. The private typehint is saved as format information to allow
    a ThingClient to reconstruct the array from the list sent over HTTP.
    """

    root: NDArray
    _labthings_typehint: str = "ndarray"
