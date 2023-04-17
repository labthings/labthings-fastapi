from __future__ import annotations
from collections.abc import Mapping, Sequence
from typing import Any, Optional

from pydantic import schema_of, parse_obj_as
from .w3c_td_model import DataSchema


JSONSchema = dict[str, Any]  # A type to represent JSONSchema


def is_a_reference(d: JSONSchema) -> bool:
    """Return True if a JSONSchema dict is a reference
    
    JSON Schema references are one-element dictionaries with
    a single key, `$ref`.  `pydantic` sometimes breaks this
    rule and so I don't check that it's a single key.
    """
    return "$ref" in d


def look_up_reference(reference: str, d: JSONSchema) -> JSONSchema:
    """Look up a reference in a JSONSchema
    
    This first asserts the reference is local (i.e. starts with #
    so it's relative to the current file), then looks up
    each path component in turn.
    """
    if not reference.startswith("#/"):
        raise NotImplementedError(
            "Built-in resolver can only dereference internal JSON references (i.e. starting with #)."
        )
    try:
        resolved: JSONSchema = d
        for key in reference[2:].split("/"):
            resolved = resolved[key]
        return resolved
    except KeyError as ke:
        raise KeyError(f"The JSON reference {reference} was not found in the schema (original error {ke}).")


def jsonschema_to_dataschema(
        d: JSONSchema, 
        root_schema: Optional[JSONSchema] = None,
        recursion_depth: int = 0,
        recursion_limit: int = 99,
    ) -> JSONSchema:
    """remove references and change field formats
    
    JSONSchema allows schemas to be replaced with `{"$ref": "#/path/to/schema"}`.
    Thing Description does not allow this. `dereference_jsonschema_dict` takes a
    `dict` representation of a JSON Schema document, and replaces all the
    references with the appropriate chunk of the file.

    JSONSchema can represent `Union` types using the `anyOf` keyword, which is
    not supported by Thing Description.  It's possible to achieve the same thing
    in the specific case of array elements, by setting `items` to a list of
    `DataSchema` objects. This function does not yet do that conversion.
    
    This generates a copy of the document, to avoid messing up `pydantic`'s cache.
    """
    root_schema = root_schema or d
    if recursion_depth > recursion_limit:
        raise ValueError(
            f"Recursion depth of {recursion_limit} exceeded - perhaps there is a circular reference?"
        )
    # JSONSchema references are one-element dictionaries, with a single key called $ref
    if is_a_reference(d):
        # We return the referenced object, calling this function again so we check for any nested references
        # inside the definition.
        return jsonschema_to_dataschema(
                look_up_reference(d["$ref"], root_schema),
                root_schema = root_schema,
                recursion_depth = recursion_depth+1,
                recursion_limit = recursion_limit
            )
    
    # TODO: convert anyOf to an array, where possible

    # After checking the object isn't a reference, we now recursively check sub-dictionaries
    # and dereference those if necessary. This could be done with a comprehension, but I
    # am prioritising readability over speed. This code is run when generating the TD, not
    # in time-critical situations.
    d_copy = {}
    for k, v in d.items():
        if isinstance(v, Mapping):
            d_copy[k] = jsonschema_to_dataschema(
                v,
                root_schema = root_schema,
                recursion_depth = recursion_depth+1,
                recursion_limit = recursion_limit
            )
        elif isinstance(v, Sequence) and len(v) > 0 and isinstance(v[0], Mapping):
            d_copy[k] = [
                jsonschema_to_dataschema(
                    item,
                    root_schema = root_schema,
                    recursion_depth = recursion_depth+1,
                    recursion_limit = recursion_limit
                ) for item in v
            ]
        else:
            d_copy[k] = v
    return d_copy


def type_to_dataschema(t: type) -> DataSchema:
    """Convert a Python type to a Thing Description DataSchema
    
    This makes use of pydantic's `schema_of` function to create a
    json schema, then applies some fixes to make a DataSchema
    as per the Thing Description (because Thing Description is
    almost but not quite compatible with JSONSchema).
    """
    schema_dict = jsonschema_to_dataschema(schema_of(t))
    # Definitions of referenced ($ref) schemas are put in a
    # key called "definitions" by pydantic. We should delete this.
    # TODO: find a cleaner way to do this
    # This shouldn't be a severe problem: we will fail with a
    # validation error if other junk is left in the schema.
    if "definitions" in schema_dict:
        del schema_dict["definitions"]
    return parse_obj_as(DataSchema, schema_dict)