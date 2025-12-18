from __future__ import annotations

from pydantic import BaseModel, RootModel
import numpy as np
from fastapi.testclient import TestClient

from labthings_fastapi.testing import create_thing_without_server
from labthings_fastapi.types.numpy import NDArray, DenumpifyingDict
import labthings_fastapi as lt


class ArrayModel(RootModel):
    root: NDArray


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


class MyNumpyThing(lt.Thing):
    """A thing that uses numpy types."""

    @lt.action
    def action_with_arrays(self, a: NDArray) -> NDArray:
        return a * 2

    @lt.action
    def read_array(self) -> NDArray:
        return np.array([1, 2])


def test_thing_description():
    """Make sure the TD validates when numpy types are used."""
    thing = create_thing_without_server(MyNumpyThing)
    assert thing.validate_thing_description() is None


def test_denumpifying_dict():
    """Check DenumpifyingDict converts arrays to lists."""
    d = DenumpifyingDict(
        root={
            "a": np.array([1, 2, 3]),
            "b": [np.arange(10), np.arange(10)],
            "c": {"ca": np.array([1, 2, 3])},
            "d": {"da": [np.arange(10), np.arange(10)]},
            "e": None,
            "f": 1,
        }
    )
    dump = d.model_dump()
    assert dump["a"] == [1, 2, 3]
    assert dump["e"] is None
    assert dump["f"] == 1
    d.model_dump_json()


def test_rootmodel():
    """Check that RootModels with NDArray convert between array and list."""
    for input in [[0, 1, 2], np.arange(3)]:
        m = ArrayModel(root=input)
        assert isinstance(m.root, np.ndarray)
        assert (m.model_dump() == [0, 1, 2]).all()


def test_numpy_over_http():
    """Read numpy array over http."""
    server = lt.ThingServer({"np_thing": MyNumpyThing})
    with TestClient(server.app) as client:
        np_thing_client = lt.ThingClient.from_url("/np_thing/", client=client)

        array = np_thing_client.read_array()
        assert isinstance(array, np.ndarray)
        assert np.array_equal(array, np.array([1, 2]))
