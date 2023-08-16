from __future__ import annotations
from typing import Any, Dict, Iterable, TYPE_CHECKING, Optional
from weakref import WeakSet
from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass
from anyio.from_thread import BlockingPortal

if TYPE_CHECKING:
    from ..thing import Thing

def class_attributes(obj: Any) -> Iterable[tuple[str, Any]]:
    """A list of all the attributes of an object's class"""
    cls = obj.__class__
    for name in dir(cls):
        yield name, getattr(cls, name)


LABTHINGS_DICT_KEY = "__labthings"

@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class LabThingsObjectData:
    property_observers: Dict[str, WeakSet] = Field(default_factory=dict)


def labthings_data(obj: Thing) -> LabThingsObjectData:
    """Get (or create) a dictionary for LabThings properties"""
    if LABTHINGS_DICT_KEY not in obj.__dict__:
        obj.__dict__[LABTHINGS_DICT_KEY] = LabThingsObjectData()
    return obj.__dict__[LABTHINGS_DICT_KEY]


def get_blocking_portal(obj: Thing) -> Optional[BlockingPortal]:
    """Retrieve a blocking portal from a Thing"""
    return obj._labthings_blocking_portal