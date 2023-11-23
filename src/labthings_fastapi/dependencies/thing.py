from __future__ import annotations
from typing import Annotated, TypeVar

from fastapi import Depends

from ..thing import Thing
from ..client.in_server import direct_thing_client_class


ThingInstance = TypeVar("ThingInstance", bound=Thing)


def direct_thing_client_dependency(
    thing_class: type[Thing],
    thing_path: str,
) -> type[Thing]:
    """A type annotation that causes FastAPI to supply a direct thing client"""
    C = direct_thing_client_class(thing_class, thing_path)
    return Annotated[C, Depends()]  # type: ignore[return-value]
