"""Thing Description module.

This module supports the generation of Thing Descriptions. Currently, the top
level function lives in `~lt.Thing.thing_description`,
but most of the supporting code is in this submodule.

A Pydantic model implementing the Thing Description is in
`.thing_description._model`, and this is used to generate our TDs -
using a `pydantic.BaseModel` helps make sure any TD errors get caught when
they are generated in Python, which makes them much easier to debug.

We also use the JSONSchema provided by W3C to validate the TDs we generate, in
`.thing_description.validation`, as a double-check that we are standards-compliant.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Optional

from pydantic import TypeAdapter, ValidationError

from labthings_fastapi.thing_description._model import DataSchema

JSONSchema = dict[str, Any]  # A type to represent JSONSchema


def is_a_reference(d: JSONSchema) -> bool:
    """Return True if a JSONSchema dict is a reference.

    JSON Schema references are one-element dictionaries with
    a single key, `$ref`.  `pydantic` sometimes breaks this
    rule and so we don't check that it's a single key.

    :param d: A JSONSchema dictionary.

    :return: ``True`` if the dictionary contains ``$ref``.
    """
    return "$ref" in d


def look_up_reference(reference: str, d: JSONSchema) -> JSONSchema:
    """Look up a reference in a JSONSchema.

    JSONSchema allows references, where chunks of JSON may be reused.
    Thing Description does not allow references, so we need to resolve
    them and paste them in-line.

    This function can only deal with local references, i.e. they must
    start with ``#`` indicating they belong to the current file.

    This function first asserts the reference is local
    (i.e. starts with # so it's relative to the current file),
    then looks up each path component in turn and returns the resolved
    chunk of JSON.

    :param reference: the local reference (should start with ``#``).
    :param d: the JSONSchema document.

    :return: the chunk of JSONSchema referenced by ``reference`` in ``d``.

    :raise KeyError: if the reference is not found in the supplied JSONSchema.
    :raise NotImplementedError: if the reference does not start with ``"#/``
        and thus is not a local reference.
    """
    if not reference.startswith("#/"):
        raise NotImplementedError(
            "Built-in resolver can only dereference internal JSON references "
            "(i.e. starting with #)."
        )
    try:
        resolved: JSONSchema = d
        for key in reference[2:].split("/"):
            resolved = resolved[key]
        return resolved
    except KeyError as ke:
        raise KeyError(
            f"The JSON reference {reference} was not found in the schema."
        ) from ke


def convert_anyof(d: JSONSchema) -> JSONSchema:
    """Convert the anyof key to oneof.

    JSONSchema makes a distinction between "anyof" and "oneof", where the former
    means "any of these fields can be present" and the latter means "exactly one
    of these fields must be present". Thing Description does not have this
    distinction, so we convert ``anyof`` to ``oneof``.


    :param d: the JSONSchema object.

    :return: a copy of ``d``, with ``anyOf`` replaced with ``oneOf``.
    """
    if "anyOf" not in d:
        return d
    out: JSONSchema = d.copy()
    out["oneOf"] = out["anyOf"]
    del out["anyOf"]
    return out


def convert_prefixitems(d: JSONSchema) -> JSONSchema:
    r"""Convert the prefixitems key to items.

    The ``items`` key in an ArraySchema_ may work in two ways:

    * If it is a `DataSchema` instance, then it specifies the schema for
      all items in the array. This would apply to ``list[int]`` for example.
    * If it is a sequence of `DataSchema` instances, then we are describing
      a `tuple` with a defined number of elements, each with a defined type,
      for example `tuple[int, str]`\ .

    JSONSchema 2020 uses `items` to mean the type of subsequent items (i.e.
    ``list[...]``), so it's only ever a single type. When describing a `tuple`
    it will use ``prefixItems`` to give the type of each element.

    JSONSchema 2019 (on which ArraySchema_ is based) has a different definition
    again, using ``items`` and ``additionalItems``\ .

    We are converting from JSONSchema 2020 (which is what `pydantic` generates)
    to ArraySchema_ so we will convert ``prefixItems`` into ``items``\ . If
    both keys are present, we will raise an error, as that's not currently
    supported.

    :param d: the JSONSchema object.

    :return: a copy of ``d``, converted to 2019 format as above.

    :raise KeyError: if we would overwrite an existing ``items``
        key.

    .. _ArraySchema: https://www.w3.org/TR/wot-thing-description/#arrayschema
    """
    if "prefixItems" not in d:
        return d
    out: JSONSchema = d.copy()
    if "items" in out:
        raise KeyError(f"Overwrote the `items` key on {out}.")
    out["items"] = out["prefixItems"]
    del out["prefixItems"]
    return out


def check_recursion(depth: int, limit: int) -> None:
    """Check the recursion count is less than the limit.

    :param depth: the current recursion depth.
    :param limit: the maximum recursion depth.

    :raise ValueError: if we exceed the recursion depth.
    """
    if depth > limit:
        raise ValueError(
            f"Recursion depth of {limit} exceeded - perhaps there is a circular "
            "reference?"
        )


def jsonschema_to_dataschema(
    d: JSONSchema,
    root_schema: Optional[JSONSchema] = None,
    recursion_depth: int = 0,
    recursion_limit: int = 99,
) -> JSONSchema:
    """Convert a data type description from JSONSchema to Thing Description.

    :ref:`wot_td` represents datatypes with DataSchemas, which are almost but not
    quite JSONSchema format. There are two main tasks to convert them:

    Resolving references
    --------------------

    JSONSchema allows schemas to be replaced with `{"$ref": "#/path/to/schema"}`.
    Thing Description does not allow this. `dereference_jsonschema_dict` takes a
    `dict` representation of a JSON Schema document, and replaces all the
    references with the appropriate chunk of the file.

    Converting union types
    ----------------------

    JSONSchema can represent `Union` types using the `anyOf` keyword, which is
    called `oneOf` by Thing Description.  It's possible to achieve the same thing
    in the specific case of array elements, by setting `items` to a list of
    `DataSchema` objects. This function does not yet do that conversion.

    This generates a copy of the document, to avoid messing up `pydantic`'s cache.

    This function runs recursively: to start with, only ``d`` should be provided
    (the input JSONSchema). We will use the other arguments to keep track of
    recursion as we convert the schema.

    :param d: a JSONSchema representation of a datatype.
    :param root_schema: the whole JSONSchema document, for resolving references.
        This will be set to ``d`` when the function is called initially.
    :param recursion_depth: how deeply this function has recursed (starts at zero).
    :param recursion_limit: how deeply this function is allowed to recurse.

    :return: the datatype in Thing Description format. This is not yet a
        `.DataSchema` instance, but may be trivially converted to one
        with ``DataSchema(**schema)``.
    """
    root_schema = root_schema or d
    check_recursion(recursion_depth, recursion_limit)
    # JSONSchema references are one-element dictionaries, with a single key called $ref
    while is_a_reference(d):
        d = look_up_reference(d["$ref"], root_schema)
        recursion_depth += 1
        check_recursion(recursion_depth, recursion_limit)

    d = convert_anyof(d)
    d = convert_prefixitems(d)

    # After checking the object isn't a reference, we now recursively check
    # sub-dictionaries and dereference those if necessary. This could be done with a
    # comprehension, but I am prioritising readability over speed. This code is run when
    # generating the TD, not in time-critical situations.
    rkwargs: dict[str, Any] = {
        "root_schema": root_schema,
        "recursion_depth": recursion_depth + 1,
        "recursion_limit": recursion_limit,
    }
    output: JSONSchema = {}
    for k, v in d.items():
        if isinstance(v, dict):
            # Any items that are Mappings (i.e. sub-dictionaries) must be recursed into
            output[k] = jsonschema_to_dataschema(v, **rkwargs)
        elif isinstance(v, Sequence) and len(v) > 0 and isinstance(v[0], Mapping):
            # We can also have lists of mappings (i.e. Array[DataSchema]), so we
            # recurse into these.
            output[k] = [jsonschema_to_dataschema(item, **rkwargs) for item in v]
        else:
            output[k] = v
    return output


def type_to_dataschema(t: type, **kwargs: Any) -> DataSchema:
    r"""Convert a Python type to a Thing Description DataSchema.

    This makes use of pydantic's `schema_of` function to create a
    json schema, then applies some fixes to make a DataSchema
    as per the Thing Description (because Thing Description is
    almost but not quite compatible with JSONSchema).

    Additional keyword arguments are added to the DataSchema,
    and will override the fields generated from the type that
    is passed in. Typically you'll want to use this for the
    `title` field.

    :param t: the Python datatype or `pydantic.BaseModel` subclass.
    :param \**kwargs: Additional keyword arguments passed to the
        `.DataSchema` constructor, often including ``title``.

    :return: a `.DataSchema` representing the type.

    :raise ValidationError: if the datatype cannot be represented
        by a `.DataSchema`.
    """
    if hasattr(t, "model_json_schema"):
        # The input should be a `BaseModel` subclass, in which case this works:
        json_schema = t.model_json_schema()
    else:
        # In principle, the below should work for any type, though some
        # deferred annotations can go wrong.
        # Some attempt at looking up the environment of functions might help
        # here.
        json_schema = TypeAdapter(t).json_schema()
    schema_dict = jsonschema_to_dataschema(json_schema)
    # Definitions of referenced ($ref) schemas are put in a
    # key called "definitions" or "$defs" by pydantic. We should delete this.
    # TODO: find a cleaner way to do this
    # This shouldn't be a severe problem: we will fail with a
    # validation error if other junk is left in the schema.
    for k in ["definitions", "$defs"]:
        if k in schema_dict:
            del schema_dict[k]
    schema_dict.update(kwargs)
    try:
        return DataSchema(**schema_dict)
    except ValidationError as ve:
        print(
            "Error while constructing DataSchema from the "
            "following dictionary:\n"
            + json.dumps(schema_dict, indent=2)
            + "Before conversion, the JSONSchema was:\n"
            + json.dumps(json_schema, indent=2)
        )
        raise ve
