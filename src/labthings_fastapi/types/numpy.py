"""Basic support for numpy arrays in Pydantic models

We define a type alias `NDArray` which is a numpy array, annotated
to allow `pydantic` to convert it to and from JSON (as an array-of-arrays).

Usage:
```
from labthings_fastapi.types.ndarray import NDArray

def double(arr: NDArray) -> NDArray:
    return arr * 2  # arr is a numpy.ndarray
```

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
from collections.abc import Mapping, Sequence


# Define a nested list of floats with 0-6 dimensions
# This would be most elegantly defined as a recursive type
# but the below gets the job done for now.
Number = Union[int, float]
NestedListOfNumbers = Union[
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
    root: NestedListOfNumbers


def np_to_listoflists(arr: np.ndarray) -> NestedListOfNumbers:
    """Convert a numpy array to a list of lists

    NB this will not be quick! Large arrays will be much better
    serialised by dumping to base64 encoding or similar.
    """
    return arr.tolist()


def listoflists_to_np(lol: Union[NestedListOfNumbers, np.ndarray]) -> np.ndarray:
    """Convert a list of lists to a numpy array (or pass-through ndarrays)"""
    return np.asarray(lol)


# Define an annotated type so Pydantic can cope with numpy
NDArray = Annotated[
    np.ndarray,
    PlainValidator(listoflists_to_np),
    PlainSerializer(np_to_listoflists, when_used="json-unless-none"),
    WithJsonSchema(NestedListOfNumbersModel.model_json_schema(), mode="validation"),
]


def denumpify(v: Any) -> Any:
    """Convert any numpy array in a dict into a list"""
    if isinstance(v, np.ndarray):
        return v.tolist()
    elif isinstance(v, Mapping):
        return {k: denumpify(vv) for k, vv in v.items()}
    elif isinstance(v, Sequence):
        return [denumpify(vv) for vv in v]
    else:
        return v


def denumpify_serializer(v: Any, nxt: SerializerFunctionWrapHandler) -> Any:
    """A Pydantic wrap serializer to denumpify mappings before serialization"""
    return nxt(denumpify(v))


class DenumpifyingDict(RootModel):
    root: Annotated[Mapping, WrapSerializer(denumpify_serializer)]
    model_config = ConfigDict(arbitrary_types_allowed=True)
