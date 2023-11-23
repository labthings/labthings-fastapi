from importlib.resources import files
import json
import jsonschema
from .. import thing_description
import time
import logging


def validate_thing_description(td: dict) -> None:
    """Validate a Thing Description.

    This accepts a dictionary (usually generated from
    `labthings_fastapi.thing_description.model.ThingDescription.model_dump()`
    ) and validates it against the JSON schema for Thing Descriptions. This is
    obtained from the W3C's Thing Description repository on GitHub, URL in the
    file.
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
    jsonschema.validate(instance=td, schema=schema)
    validated_td = time.time()
    logging.info(
        f"Thing Description validated OK (schema load: {loaded_schema-start:.1f}s, "
        f"schema validation: {validated_schema-loaded_schema:.1f}s, TD validation: "
        f"{validated_td-validated_schema:.1f}s)"
    )
