from __future__ import annotations

from pydantic import BaseModel
import numpy as np

from labthings_fastapi.types.numpy import NDArray
from labthings_fastapi.thing import Thing
from labthings_fastapi.decorators import thing_action


def check_field_works_with_list(data):
    class Model(BaseModel):
        a: NDArray

    m = Model(a=data)
    assert isinstance(m.a, np.ndarray)
    d = m.model_dump()
    assert (d["a"] == data).all()
    m.model_json_schema()
    m.model_dump_json()


def check_field_works_with_ndarray(data):
    class Model(BaseModel):
        a: NDArray

    m = Model(a=data)
    assert isinstance(m.a, np.ndarray)
    d = m.model_dump()
    assert (d["a"] == data.tolist()).all()
    m.model_json_schema()
    m.model_dump_json()


def test_1d():
    check_field_works_with_list([1])
    check_field_works_with_list([1, 2, 3])
    check_field_works_with_list(np.arange(10))


def test_3d():
    check_field_works_with_list([[[1]]])
    check_field_works_with_list([[[2]]])


def test_2d():
    check_field_works_with_list([[1, 2]])


def test_0d():
    class Model(BaseModel):
        a: NDArray

    m = Model(a=1)
    assert m.a == 1
    d = m.model_dump()
    assert d["a"] == 1
    m.model_json_schema()
    m.model_dump_json()


class MyNumpyThing(Thing):
    @thing_action
    def action_with_arrays(self, a: NDArray) -> NDArray:
        return a * 2


def test_thing_description():
    thing = MyNumpyThing()
    assert thing.validate_thing_description() is None
