from __future__ import annotations
from typing import Any, Dict, Iterable, TYPE_CHECKING, Optional
from weakref import WeakSet
from pydantic import BaseModel, ConfigDict, Field, RootModel, create_model
from pydantic.dataclasses import dataclass
from anyio.from_thread import BlockingPortal

if TYPE_CHECKING:
    from ..thing import Thing


def class_attributes(obj: Any) -> Iterable[tuple[str, Any]]:
    """A list of all the attributes of an object's class"""
    cls = obj.__class__
    for name in dir(cls):
        if name.startswith("__"):
            continue
        yield name, getattr(cls, name)


def attributes(cls: Any) -> Iterable[tuple[str, Any]]:
    """A list of all the attributes of an object not starting with `__`"""
    for name in dir(cls):
        if name.startswith("__"):
            continue
        yield name, getattr(cls, name)


LABTHINGS_DICT_KEY = "__labthings"


@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class LabThingsObjectData:
    property_observers: Dict[str, WeakSet] = Field(default_factory=dict)
    action_observers: Dict[str, WeakSet] = Field(default_factory=dict)


def labthings_data(obj: Thing) -> LabThingsObjectData:
    """Get (or create) a dictionary for LabThings properties"""
    if LABTHINGS_DICT_KEY not in obj.__dict__:
        obj.__dict__[LABTHINGS_DICT_KEY] = LabThingsObjectData()
    return obj.__dict__[LABTHINGS_DICT_KEY]


def get_blocking_portal(obj: Thing) -> Optional[BlockingPortal]:
    """Retrieve a blocking portal from a Thing"""
    return obj._labthings_blocking_portal


def wrap_plain_types_in_rootmodel(model: type) -> type[BaseModel]:
    """Ensure a type is a subclass of BaseModel.

    If a `BaseModel` subclass is passed to this function, we will pass it
    through unchanged. Otherwise, we wrap the type in a RootModel.
    In the future, we may explicitly check that the argument is a type
    and not a model instance.
    """
    try:  # This needs to be a `try` as basic types are not classes
        assert issubclass(model, BaseModel)
        return model
    except (TypeError, AssertionError):
        return create_model(f"{model!r}", root=(model, ...), __base__=RootModel)
