from __future__ import annotations
from typing import Annotated, Any, Callable
from collections.abc import Mapping

from fastapi import Depends, Request

from ..server import find_thing_server


def thing_states_getter(request: Request) -> Callable[[], Mapping[str, Any]]:
    """A dependency to retrieve summary metadata from all Things in this server.

    This is intended to make it easy for a Thing to summarise the other Things
    it's associated with, for example it's used to populate the UserComment
    EXIF field in the OpenFlexure Microscope.

    `thing_states_getter` differs from `get_thing_states` because the latter
    is evaluated once, before the action, and this dependency returns a function
    that collects the metadata when it's run.

    If your action is likely to be run from other actions where the metadata
    changes, you should use this version.
    """
    server = find_thing_server(request.app)

    def get_metadata():
        """Retrieve metadata from each Thing"""
        return {k: v.thing_state for k, v in server.things.items()}

    return get_metadata


GetThingStates = Annotated[
    Callable[[], Mapping[str, Any]], Depends(thing_states_getter)
]
