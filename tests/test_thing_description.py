"""Tests for the thing_description submodule.

The `.thing_description` module is mostly tested by other files in the test suite.
This file checks a validation function that's not currently used (as we validate
against the JSONSchema directly, rather than my port of it to Pydantic).
"""

import pytest
import labthings_fastapi.thing_description._model as model

OLD_CONTEXT = "https://www.w3.org/2019/wot/td/v1"
CONTEXT = "https://www.w3.org/2022/wot/td/v1.1"


@pytest.mark.parametrize(
    "value",
    [
        CONTEXT,
        [CONTEXT],
        [CONTEXT, {"@language": "en"}],
        [OLD_CONTEXT, CONTEXT],
        [OLD_CONTEXT, CONTEXT, "https://something.else/context"],
    ],
)
def test_thing_context_valid(value):
    """Test the uses_thing_context validator.

    Note that ``model.uses_thing_context`` is a pydantic validator, so it either
    returns ``None`` or raises an exception.

    This validation logic should reproduce what's done in the JSON Schema provided
    by W3C, which is included in the ``thing_description`` submodule.
    """
    assert model.uses_thing_context(value) is None


@pytest.mark.parametrize(
    "value",
    [
        OLD_CONTEXT,
        [OLD_CONTEXT],
        [CONTEXT, OLD_CONTEXT],
        "https://some.url/",
        "a random string",
        {"key": "value"},
        ["a list of strings", "with two elements"],
    ],
)
def test_thing_context_invalid(value):
    """Test invalid values fail to be validated as thing contexts."""
    with pytest.raises(ValueError):
        model.uses_thing_context(value)
