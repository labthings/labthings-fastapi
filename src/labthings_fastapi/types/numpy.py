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
    RootModel,
    SerializerFunctionWrapHandler,
    WrapSerializer,
)
from typing import Annotated, Any, Union, TypeAlias
from collections.abc import Mapping, Sequence

from pydantic_numpy.typing import NpNDArray  # type: ignore

# This is here for backwards compatibility. Ideally, we should just
# use types from `pydantic_numpy.typing` directly.
NDArray: TypeAlias = Union[NpNDArray, int, float]


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
