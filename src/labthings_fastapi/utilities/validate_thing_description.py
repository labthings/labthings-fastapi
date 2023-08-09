from importlib.resources import files
import json
import jsonschema
from .. import utilities

def validate_thing_description(thing_description: dict):
        with files(utilities).joinpath("td-json-schema-validation.json").open('r') as f:
                schema = json.load(f)
        jsonschema.Draft7Validator.check_schema(schema)
        # Decode the JSON back into a primitive dictionary
        # Validate
        return jsonschema.validate(instance=thing_description, schema=schema)