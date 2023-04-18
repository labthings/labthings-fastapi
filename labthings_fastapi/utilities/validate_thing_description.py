from importlib import resources
import json

import jsonschema

from .. import utilities

def validate_thing_description(thing_description: dict):
        schema = json.load(resources.open_text(utilities, "w3c_td_schema.json"))
        jsonschema.Draft7Validator.check_schema(schema)
        # Decode the JSON back into a primitive dictionary
        # Validate
        return jsonschema.validate(instance=thing_description, schema=schema)