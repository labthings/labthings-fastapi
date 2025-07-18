"""Validate a generated Thing Description against the W3C schema.

We generate :ref:`wot_td` using `pydantic` models so there is a layer of
validation applied every time one is created. However, this module allows
the generated JSON document to be formally validated against the schema
in the W3C specification, as an additional check.

See :ref:`wot_td` for a link to the specification in human-readable format.
"""

from importlib.resources import files
import json
import jsonschema
import jsonschema.exceptions
from .. import thing_description
import time
import logging


def validate_thing_description(td: dict) -> None:
    """Validate a Thing Description.

    This accepts a dictionary (usually generated from
    `labthings_fastapi.thing_description._model.ThingDescription.model_dump()`
    ) and validates it against the JSON schema for Thing Descriptions. This is
    obtained from the W3C's Thing Description repository on GitHub, URL in the
    file.

    No return value is provided, but a `~jsonschema.exceptions.ValidationError`
    is raised if the schema is invalid.

    :param td: the Thing Description to be validated.

    :raise jsonschema.exceptions.ValidationError: if the Thing Description is
        invalid.
    """
    start = time.time()
    td_file = files(thing_description).joinpath("td-json-schema-validation.json")
    with td_file.open("r") as f:
        schema = json.load(f)
    loaded_schema = time.time()
    # Check the schema itself is valid
    jsonschema.Draft7Validator.check_schema(schema)
    validated_schema = time.time()
    # Validate the TD dictionary
    try:
        jsonschema.validate(instance=td, schema=schema)
    except jsonschema.exceptions.ValidationError as e:
        raise e
    validated_td = time.time()
    logging.debug(
        f"Thing Description validated OK (schema load: {loaded_schema - start:.1f}s, "
        f"schema validation: {validated_schema - loaded_schema:.1f}s, TD validation: "
        f"{validated_td - validated_schema:.1f}s)"
    )
