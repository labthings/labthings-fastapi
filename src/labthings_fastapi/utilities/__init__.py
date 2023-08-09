from typing import Any, Dict
from weakref import WeakSet
from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass

def class_attributes(obj: Any) -> iter:
    """A list of all the attributes of an object's class"""
    cls = obj.__class__
    for name in dir(cls):
        yield name, getattr(cls, name)


LABTHINGS_DICT_KEY = "__labthings"

@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class LabThingsObjectData:
    property_observers: Dict[str, WeakSet] = Field(default_factory=dict)


def labthings_data(obj: Any) -> LabThingsObjectData:
    """Get (or create) a dictionary for LabThings properties"""
    if LABTHINGS_DICT_KEY not in obj.__dict__:
        obj.__dict__[LABTHINGS_DICT_KEY] = LabThingsObjectData()
    return obj.__dict__[LABTHINGS_DICT_KEY]