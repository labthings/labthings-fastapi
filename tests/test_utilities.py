from pydantic import BaseModel, RootModel
from labthings_fastapi.utilities import model_to_dict
from labthings_fastapi.utilities.introspection import EmptyInput
import pytest


def test_model_to_dict():
    class MyModel(BaseModel):
        foo: str
        bar: int

    assert model_to_dict(MyModel(foo="a", bar=0)) == {
        "foo": "a",
        "bar": 0,
    }

    class NonEmptyRootModel(RootModel):
        root: str

    with pytest.raises(ValueError):
        model_to_dict(NonEmptyRootModel("a"))

    d = model_to_dict(EmptyInput())
    assert d == {}
