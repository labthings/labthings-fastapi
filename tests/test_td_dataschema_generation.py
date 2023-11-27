from __future__ import annotations
from labthings_fastapi.thing_description import type_to_dataschema

import json
from pydantic import BaseModel
from typing import Optional
from labthings_fastapi.thing_description.model import DataSchema


def ds_json_dict(ds: DataSchema) -> dict:
    """Serialise a DataSchema to json and reinflate to a dict

    This removes complicated types so we end up with a simple
    representation that's slightly more abstracted from the
    implementation details - e.g. enums are reduced to their
    simple types. This is appropriate if we're testing against
    what we'd expect to see in the API.
    """
    return json.loads(ds.model_dump_json())


def test_int():
    ds = type_to_dataschema(int)
    j = ds_json_dict(ds)
    assert j["type"] == "integer"


def test_float():
    ds = type_to_dataschema(float)
    j = ds_json_dict(ds)
    assert j["type"] == "number"


def test_str():
    ds = type_to_dataschema(str)
    j = ds_json_dict(ds)
    assert j["type"] == "string"


def test_none():
    ds = type_to_dataschema(type(None))
    j = ds_json_dict(ds)
    assert j["type"] == "null"


def test_array():
    ds = type_to_dataschema(list[int])
    j = ds_json_dict(ds)
    assert j["type"] == "array"
    assert j["items"]["type"] == "integer"


# This is an annoying edge case where Thing Description
# and JSONSchema differ. For now, it is simply not
# supported so I won't test for it.
# If anyone tries it, they'll get an error rather than
# incorrect behaviour.
# def test_array_union():
#    ds = type_to_dataschema(list[Union[int, str]])
#    j = ds_json_dict(ds)
#    assert j["type"] == "array"
#    assert j["items"][0]["type"] == "integer"
#    assert j["items"][1]["type"] == "string"


def test_boolean():
    ds = type_to_dataschema(bool)
    j = ds_json_dict(ds)
    assert j["type"] == "boolean"


def test_object():
    class A(BaseModel):
        a: int
        b: Optional[int] = None

    ds = type_to_dataschema(A)
    j = ds_json_dict(ds)
    assert j["type"] == "object"
    assert "a" in j["required"]
    assert "b" not in j["required"]


def test_nested_object():
    class A(BaseModel):
        a: int
        b: Optional[int] = None

    class B(BaseModel):
        first_child: A
        second_child: A

    # locally-defined models can confuse pydantic, so we pass
    # in A explicitly to convert annotations into types.
    B.model_rebuild(_types_namespace={"A": A})

    ds = type_to_dataschema(B)
    j = ds_json_dict(ds)
    assert j["type"] == "object"
    assert j["properties"]["first_child"]["type"] == "object"
    assert j["properties"]["first_child"]["properties"]["a"]["type"] == "integer"
