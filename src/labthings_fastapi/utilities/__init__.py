"""Utility functions used by LabThings-FastAPI."""

from __future__ import annotations
from typing import Any, Dict, Iterable, TYPE_CHECKING, Optional
from weakref import WeakSet
from pydantic import BaseModel, ConfigDict, Field, RootModel, create_model
from pydantic.dataclasses import dataclass
from anyio.from_thread import BlockingPortal
from .introspection import EmptyObject

if TYPE_CHECKING:
    from ..thing import Thing


def class_attributes(obj: Any) -> Iterable[tuple[str, Any]]:
    """List all the attributes of an object's class.

    This function gets all class attributes, including inherited ones.
    It is used to obtain the various descriptors used to represent
    properties and actions. It calls `.attributes` on ``obj.__class__``.

    :param obj: The instance, usually a `.Thing` instance.

    :yield: tuples of ``(name, value)`` giving each attribute of the class.
    """
    cls = obj.__class__
    yield from attributes(cls)


def attributes(cls: Any) -> Iterable[tuple[str, Any]]:
    """List all the attributes of an object not starting with `__`.

    :param cls: The object whose attributes we are listing. This may be
        a class, because classes are objects too.

    :yield: tuples of ``(name, value)`` giving each attribute and its
        value.
    """
    for name in dir(cls):
        if name.startswith("__"):
            continue
        yield name, getattr(cls, name)


LABTHINGS_DICT_KEY = "__labthings"


@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class LabThingsObjectData:
    r"""Data used by LabThings, stored on each `.Thing`.

    This `pydantic.dataclass` groups together some properties used
    by LabThings descriptors, to avoid cluttering the namespace of the
    `.Thing` subclass on which they are defined.
    """

    property_observers: Dict[str, WeakSet] = Field(default_factory=dict)
    r"""The observers added to each property.

    Keys are property names, values are weak sets used by `.DataProperty`\ .
    """
    action_observers: Dict[str, WeakSet] = Field(default_factory=dict)
    r"""The observers added to each action.

    Keys are action names, values are weak sets used by
    `.ActionDescriptor`\ .
    """


def labthings_data(obj: Thing) -> LabThingsObjectData:
    """Get (or create) a dictionary for LabThings properties.

    Ensure there is a `.LabThingsObjectData` dataclass attached to
    a particular `.Thing`, and return it.

    :param obj: The `.Thing` we are looking for the dataclass on.

    :return: a `.LabThingsObjectData` instance attached to ``obj``.
    """
    if LABTHINGS_DICT_KEY not in obj.__dict__:
        obj.__dict__[LABTHINGS_DICT_KEY] = LabThingsObjectData()
    return obj.__dict__[LABTHINGS_DICT_KEY]


def get_blocking_portal(obj: Thing) -> Optional[BlockingPortal]:
    """Retrieve a blocking portal from a Thing.

    See :ref:`concurrency` for more details.

    When a `.Thing` is attached to a `.ThingServer` and the `.ThingServer`
    is started, it sets an attribute on each `.Thing` to allow it to
    access an `anyio.from_thread.BlockingPortal`. This allows threaded
    code to call async code.

    This function retrieves the blocking portal from a `.Thing`.

    :param obj: the `.Thing` on which we are looking for the portal.

    :return: the blocking portal.
    """
    return obj._labthings_blocking_portal


def wrap_plain_types_in_rootmodel(model: type) -> type[BaseModel]:
    """Ensure a type is a subclass of BaseModel.

    If a `pydantic.BaseModel` subclass is passed to this function, we will pass it
    through unchanged. Otherwise, we wrap the type in a `pydantic.RootModel`.
    In the future, we may explicitly check that the argument is a type
    and not a model instance.

    :param model: A Python type or `pydantic` model.

    :return: A `pydantic` model, wrapping Python types in a ``RootModel`` if needed.
    """
    try:  # This needs to be a `try` as basic types are not classes
        assert issubclass(model, BaseModel)
        return model
    except (TypeError, AssertionError):
        return create_model(f"{model!r}", root=(model, ...), __base__=RootModel)


def model_to_dict(model: Optional[BaseModel]) -> Dict[str, Any]:
    """Convert a pydantic model to a dictionary, non-recursively.

    We convert only the top level model, i.e. we do not recurse into submodels.
    This is important to avoid serialising Blob objects in action inputs.
    This function returns `dict(model)`, with exceptions for the case of `None`
    (converted to an empty dictionary) and `pydantic.RootModel` (checked to see
    if they correspond to empty input).

    If `pydantic.RootModel` with non-empty input is allowed, this function will
    need to be updated to handle them.

    :param model: A Pydantic model (usually the input of an action).

    :return: A dictionary with string keys, which are the fields of the model.
        This should be suitable for using as ``**kwargs`` to an action.

    :raise ValueError: if we are given a root model that isn't empty.
    """
    if model is None:
        return {}
    if isinstance(model, RootModel):
        if model.root is None:
            return {}
        if isinstance(model.root, EmptyObject):
            return {}
        raise ValueError("RootModels with non-empty input are not supported")
    return dict(model)
