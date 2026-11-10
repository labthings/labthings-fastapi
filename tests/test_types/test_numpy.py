"""Test the numpy types.

This module tests the new model and annotated type for numpy arrays.
It's intended that the old tests (`../test_numpy_type.py`) will be
removed once the old types are retired.
"""

from datetime import datetime
from typing import Annotated

import numpy as np
import pytest
from pydantic import RootModel

from labthings_fastapi.types.numpy import Base64NDArrayModel, NDArrayAnnotation

ARRAYS = (
    [np.arange(0, 255, dtype=d) for d in [np.uint8, np.uint16, np.uint32, np.uint64]]
    + [np.arange(-100, 100, dtype=d) for d in [np.int8, np.int16, np.int32, np.int64]]
    + [
        3 ** np.arange(-5, 5, dtype=d)
        for d in [np.float16, np.float32, np.float64, np.float128]
    ]
    + [
        np.array([0.4 + 0.7j, 35 + 85j, 89, -49j], dtype=d)
        for d in [np.complex64, np.complex128, np.complex256]
    ]
    + [np.array([False, True, False, True], dtype=np.bool)]
    + [
        np.array(1000),  # scalar int
        np.array(10.0),  # scalar float
    ]
    + [
        np.array([0.0, 1.0, np.inf, -np.inf, np.nan])  # special float values
    ]
)


UNSUPPORTED_ARRAYS = [
    # Record arrays aren't supported
    np.array([(1.0, 2), (3.0, 4)], dtype=[("x", "<f8"), ("y", "<i8")]),
    # Object arrays aren't supported
    np.array([None, object()]),
    # Datetime and timedelta aren't supported
    np.array([datetime.now()]),
    np.array([datetime.now() - datetime.fromtimestamp(0)]),
    # Strings aren't supported
    np.array(["an", "array", "of", "strings"]),
    # Bytes aren't supported
    np.array(b"01234"),
]


FIELDS = {
    "element_type",
    "element_length",
    "byte_order",
    "shape",
    "array_order",
    "data",
}


@pytest.mark.parametrize("array", ARRAYS)
def test_array_roundtrip_json(array):
    """Check an array can be serialised and reconstructed from JSON."""
    model = Base64NDArrayModel.from_array(array)
    json = model.model_dump_json()
    reconstructed = Base64NDArrayModel.model_validate_json(json)
    reconstructed_array = reconstructed.to_array()
    assert array.dtype == reconstructed_array.dtype
    assert array.dtype.descr == reconstructed_array.dtype.descr
    assert np.array_equal(array, reconstructed_array, equal_nan=True)


@pytest.mark.parametrize("array", ARRAYS)
def test_array_roundtrip_python(array):
    """Check an array can be serialised and reconstructed from Python."""
    model = Base64NDArrayModel.from_array(array)
    json = model.model_dump()
    reconstructed = Base64NDArrayModel.model_validate(json)
    reconstructed_array = reconstructed.to_array()
    assert array.dtype == reconstructed_array.dtype
    assert array.dtype.descr == reconstructed_array.dtype.descr
    assert np.array_equal(array, reconstructed_array, equal_nan=True)


@pytest.mark.parametrize("array", UNSUPPORTED_ARRAYS)
def test_array_unsupported(array):
    """Check unsupported arrays give a good exception."""
    with pytest.raises(ValueError, match="not supported"):
        Base64NDArrayModel.from_array(array)


@pytest.mark.parametrize("array", ARRAYS)
def test_rootmodel_annotation(array):
    """Test that the annotated type validates and serialises correctly in Python."""

    class NDArrayRootModel(RootModel):
        root: Annotated[np.ndarray, NDArrayAnnotation]

    model = NDArrayRootModel(array)
    dumped = model.model_dump()
    assert set(dumped.keys()) == FIELDS
    reconstructed = NDArrayRootModel.model_validate(dumped)
    reconstructed_array = reconstructed.root
    assert array.dtype == reconstructed_array.dtype
    assert array.dtype.descr == reconstructed_array.dtype.descr
    assert np.array_equal(array, reconstructed_array, equal_nan=True)


@pytest.mark.parametrize("array", ARRAYS)
def test_rootmodel_annotatio_json(array):
    """Test that the annotated type validates and serialises correctly in JSON."""

    class NDArrayRootModel(RootModel):
        root: Annotated[np.ndarray, NDArrayAnnotation]

    model = NDArrayRootModel(array)
    dumped = model.model_dump_json()
    for field in FIELDS:
        assert field in dumped
    reconstructed = NDArrayRootModel.model_validate_json(dumped)
    reconstructed_array = reconstructed.root
    assert array.dtype == reconstructed_array.dtype
    assert array.dtype.descr == reconstructed_array.dtype.descr
    assert np.array_equal(array, reconstructed_array, equal_nan=True)
