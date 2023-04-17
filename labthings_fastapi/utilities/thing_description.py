from typing import Any

from pydantic import schema_of
from .w3c_td_model import DataSchema


def type_to_dataschema(t) -> DataSchema:
    schema_dict = schema_of(t)
    return DataSchema(**schema_dict)