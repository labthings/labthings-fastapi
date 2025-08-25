"""Tests for the utilities module.

This should grow over time. It would also be nice to figure out a way of
checking that the utilities module is covered by other tests - because if
it's not, it may mean those utility functions should be removed as they
are not used.
"""

from pydantic import BaseModel, RootModel
import pytest
from labthings_fastapi import utilities
from labthings_fastapi.utilities.introspection import EmptyObject


class OptionalInt(RootModel):
    """A RootModel for a type that allows None."""

    root: int | None = None


class EmptyRootModel(RootModel):
    """A RootModel that may contain an EmptyObject."""

    root: EmptyObject | str


class MyModel(BaseModel):
    a: int = 1
    b: str = "two"
    c: OptionalInt = 1


def test_model_to_dict():
    """Check we can non-recursively convert Pydantic models to dictionaries."""
    assert utilities.model_to_dict(None) == {}
    assert utilities.model_to_dict(EmptyObject()) == {}

    # A meaningful object should turn into a dictionary, but sub-models
    # should stay as models.
    d1 = utilities.model_to_dict(MyModel(a=5, b="b", c=None))
    assert set(d1.keys()) == {"a", "b", "c"}
    assert d1["a"] == 5
    assert d1["b"] == "b"
    # c should **not** be None, as the conversion isn't recursive, it should
    # be a model instance.
    assert isinstance(d1["c"], OptionalInt)
    assert d1["c"].root is None

    # RootModels that evaluate to None are allowed
    assert utilities.model_to_dict(OptionalInt(None)) == {}
    assert utilities.model_to_dict(EmptyRootModel(EmptyObject())) == {}

    # RootModels that don't evaluate to None are not allowed
    with pytest.raises(ValueError):
        utilities.model_to_dict(EmptyRootModel("foo"))
    with pytest.raises(ValueError):
        utilities.model_to_dict(OptionalInt(0))
