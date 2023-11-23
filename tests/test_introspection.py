import pytest
from labthings_fastapi.utilities.introspection import (
    input_model_from_signature,
    StrictEmptyInput,
    EmptyInput,
)


def test_no_args():
    def fun():
        pass

    m = input_model_from_signature(fun)
    assert m == StrictEmptyInput


def test_only_kwargs():
    def fun(**kwargs):
        pass

    m = input_model_from_signature(fun)
    assert m == EmptyInput
    m()  # No input is required
    m(foo="bar")  # But input is allowed


def test_kwargs_and_args():
    def fun(foo, **kwargs):
        pass

    m = input_model_from_signature(fun)
    assert m.model_config["extra"] == "allow"
    assert "foo" in m.model_fields
    assert len(m.model_fields) == 1


def test_varargs():
    def fun(*args):
        pass

    with pytest.raises(TypeError):
        input_model_from_signature(fun)
