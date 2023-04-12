from importlib import resources
import json

import jsonschema

from .. import utilities

def validate_thing_description(thing_description: str):
        schema = json.load(resources.open_text(utilities, "w3c_td_schema.json"))
        jsonschema.Draft7Validator.check_schema(schema)
        # Decode the JSON back into a primitive dictionary
        td_json_dict = json.loads(thing_description)
        # Validate
        jsonschema.validate(instance=td_json_dict, schema=schema)