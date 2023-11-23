from __future__ import annotations

from pydantic import BaseModel
import numpy as np

from labthings_fastapi.types.numpy import NDArray


def test_ndarray_field():
    class Model(BaseModel):
        a: NDArray

    m = Model(a=[[[1]]])
    assert isinstance(m.a, np.ndarray)
    d = m.model_dump()
    assert d["a"] == [[[1]]]
    m.model_json_schema()
    m.model_dump_json()
