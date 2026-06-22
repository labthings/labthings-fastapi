from __future__ import annotations

import json
from typing import Any, Literal

import pytest
from pydantic import BaseModel

from labthings_fastapi.thing_description import type_to_dataschema
from labthings_fastapi.thing_description._model import DataSchema


class A(BaseModel):
    """A model used to check the schema generates OK."""

    a: int
    b: int | None = None
    """Note that `b` is optional."""


class B(BaseModel):
    """A model use to check the schema may nest other models."""

    first_child: A
    second_child: A


class C(BaseModel):
    """A model where extra properties are allowed."""

    model_config = {"extra": "allow"}
    a: int


def ds_json_dict(ds: DataSchema) -> dict:
    """Serialise a DataSchema to json and reinflate to a dict

    This removes complicated types so we end up with a simple
    representation that's slightly more abstracted from the
    implementation details - e.g. enums are reduced to their
    simple types. This is appropriate if we're testing against
    what we'd expect to see in the API.
    """
    return json.loads(
        ds.model_dump_json(
            exclude_none=True,
        )
    )


@pytest.mark.parametrize(
    ("python_type", "schema_dict"),
    [
        (Any, {}),
        (int, {"type": "integer"}),
        (float, {"type": "number"}),
        (str, {"type": "string"}),
        (bool, {"type": "boolean"}),
        (None, {"type": "null"}),
        # Literal should turn into a JSON "enum"
        (Literal[1, 2], {"type": "integer", "enum": [1, 2]}),
        (Literal["a", "b"], {"type": "string", "enum": ["a", "b"]}),
        # Unions should use "oneOf"
        (int | str, {"oneOf": [{"type": "integer"}, {"type": "string"}]}),
        (None | str, {"oneOf": [{"type": "string"}, {"type": "null"}]}),
        # lists and dicts/models are more complicated, because they're generic
        (list, {"type": "array", "items": {}}),
        (list[int], {"type": "array", "items": {"type": "integer"}}),
        (
            list[int | str],  # A list of union types should use "oneOf"
            {
                "type": "array",
                "items": {"oneOf": [{"type": "integer"}, {"type": "string"}]},
            },
        ),
        # a dictionary should be represented as a JSON object.
        (dict, {"type": "object"}),
        (dict[int, str], {"type": "object"}),  # at present, type subscripts get ignored
        pytest.param(
            dict[Literal["a", "b"], int],
            {},
            marks=pytest.mark.xfail(reason="Issue #355"),
        ),
        # A model also becomes an "object" but it has defined "properties".
        (
            A,  # This is a relatively simple object (each property is a simple type)
            {
                "description": "A model used to check the schema generates OK.",
                "type": "object",
                "properties": {
                    "a": {"title": "A", "type": "integer"},
                    "b": {
                        "title": "B",
                        "oneOf": [{"type": "integer"}, {"type": "null"}],
                    },
                },
                "required": ["a"],  # Note: "b" is optional, so should not be listed.
                "title": "A",
            },
        ),
        (
            B,  # This features nested sub-models, which are expanded in-line.
            {
                "description": "A model use to check the schema may nest other models.",
                "properties": {
                    "first_child": {
                        "description": "A model used to check the schema generates OK.",
                        "properties": {
                            "a": {"title": "A", "type": "integer"},
                            "b": {
                                "oneOf": [{"type": "integer"}, {"type": "null"}],
                                "title": "B",
                            },
                        },
                        "required": ["a"],
                        "title": "A",
                        "type": "object",
                    },
                    "second_child": {
                        "description": "A model used to check the schema generates OK.",
                        "properties": {
                            "a": {"title": "A", "type": "integer"},
                            "b": {
                                "oneOf": [{"type": "integer"}, {"type": "null"}],
                                "title": "B",
                            },
                        },
                        "required": ["a"],
                        "title": "A",
                        "type": "object",
                    },
                },
                "required": ["first_child", "second_child"],
                "title": "B",
                "type": "object",
            },
        ),
        (
            C,
            {
                "title": "C",
                "description": "A model where extra properties are allowed.",
                "properties": {"a": {"title": "A", "type": "integer"}},
                "required": ["a"],
                "type": "object",
                # Currently, there's no indication of whether extra properties
                # are allowed or not.
            },
        ),
    ],
)
def test_types(python_type, schema_dict):
    """Check the schemas generated for a collection of simple types."""
    ds = type_to_dataschema(python_type)
    assert ds_json_dict(ds) == schema_dict
