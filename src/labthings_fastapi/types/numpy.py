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
"""
from __future__ import annotations
import numpy as np
from pydantic import (
    BeforeValidator,
    PlainSerializer,
    RootModel,
    WithJsonSchema,
)
import pydantic.json_schema
from enum import StrEnum
from typing import Annotated, Dict, List, Optional, Tuple, Union

# Define a nested list of floats with 0-6 dimensions
# This would be most elegantly defined as a recursive type
# but the below gets the job done for now.
Number = Union[int, float, complex]
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

def listoflists_to_np(lol: NestedListOfNumbers) -> np.ndarray:
    """Convert a list of lists to a numpy array"""
    return np.asarray(lol)

# Define an annotated type so Pydantic can cope with numpy
NDArray = Annotated[
    np.ndarray,
    BeforeValidator(listoflists_to_np),
    PlainSerializer(np_to_listoflists, when_used="json-unless-none"),
    WithJsonSchema(NestedListOfNumbersModel.model_json_schema(), mode="validation"),
]
