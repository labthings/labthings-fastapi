"""Convert Thing Description datatypes into Python types

This is a partial implementation of the Thing Description specification,
producing Python type annotations based on DataSchema objects. It is
incomplete and deliberately errs on the side of being permissive: I
anticipate it will mostly be useful when using generated client code.
"""
from __future__ import annotations
from .model import DataSchema
from typing import Union, Mapping, Sequence

SIMPLE_TYPE_MAPPING = {
    "string": str,
    "integer": int,
    "boolean": bool,
    "number": float,
    "null": type(None),
}

def td_to_python_type(schema: DataSchema) -> type:
    """Take a DataSchema and return a Python type"""
    if schema.field_type in SIMPLE_TYPE_MAPPING:
        return SIMPLE_TYPE_MAPPING[schema.field_type]
    if schema.field_type is None:
        if schema.oneOf is not None:
            return Union[tuple(td_to_python_type(s) for s in schema.oneOf)]
        else:
            raise ValueError("Cannot convert schema with no type and no oneOf")
    elif schema.field_type == "object":
        return Mapping  # or Any? Or a Pydantic model?
    elif schema.field_type == "array":
        if isinstance(schema.items, DataSchema):
            return Sequence[td_to_python_type(schema.items)]
        else:
            raise NotImplementedError("Multi-type arrays are not yet supported")
    