from __future__ import annotations
from typing import Annotated, Optional

from fastapi import Depends

from ..thing import Thing
from ..client.in_server import direct_thing_client_class


def direct_thing_client_dependency(
    thing_class: type[Thing],
    thing_path: str,
    actions: Optional[list[str]] = None,
) -> type[Thing]:
    """A type annotation that causes FastAPI to supply a direct thing client

    :param thing_class: The class of the thing to connect to
    :param thing_path: The path to the thing on the server
    :param actions: The actions that the client should be able to perform.
        If this is specified, only those actions will be available. If it is
        `None` (default), all actions will be available.

        Note that the dependencies of all available actions will be added to
        your endpoint - so it is best to only specify the actions you need, in
        order to avoid spurious extra dependencies.
    :return: A type annotation that will cause FastAPI to supply a direct thing client
    """
    C = direct_thing_client_class(thing_class, thing_path, actions=actions)
    return Annotated[C, Depends()]  # type: ignore[return-value]
