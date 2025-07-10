"""FastAPI dependency to get metadata from all Things.

This module defines a FastAPI dependency (see dependencies_) that will
retrieve metadata from every `.Thing` on the server. This is intended to
simplify the task of adding metadata to data collected by `.Thing` instances.
"""

from __future__ import annotations
from typing import Annotated, Any, Callable
from collections.abc import Mapping

from fastapi import Depends, Request

from .thing_server import find_thing_server


def thing_states_getter(request: Request) -> Callable[[], Mapping[str, Any]]:
    """Generate a function to retrieve metadata from all Things in this server.

    This is intended to make it easy for a `.Thing` to summarise the other
    `.Things` in the same server, as is often appropriate when embedding metadata
    in data files. For example, it's used to populate the ``UserComment``
    EXIF field in images saved by the OpenFlexure Microscope.

    This is intended for use as a FastAPI dependency, so the ``request`` argument
    will be supplied automatically.

    This function does not collect the metadata when it is run. Instead, we
    return a function that will collect the metadata when it is called. This
    delays collection of metadata until it is needed.

    Delaying collection of metadata is useful because FastAPI dependencies are
    evaluated only once, before the action starts. If we collect metadata then,
    there is no way for it to change during an action, so the metadata may be
    out of date.

    For example, if we take
    a Z stack of microscope images, we need to collect metadata after each image
    in order to ensure the recorded position of the stage is up to date.

    Bear in mind that actions may call other actions, so even if you have
    a very simple or short action that will not cause metadata to change, it
    may be called by a longer action where that isn't true. Dependencies will be
    evaluated before the calling action starts, so stale metadata is still a
    possibility in very short actions.

    :param request: the `fastapi.Request` object, supplied automatically when
        used as a dependency. See dependencies_.

    :return: a function that returns a dictionary of metadata.
    """
    server = find_thing_server(request.app)

    def get_metadata() -> dict[str, Any]:
        """Retrieve metadata from all Things on the server.

        :return: a dictionary of metadata, with the `.Thing` names as keys.
        """
        return {k: v.thing_state for k, v in server.things.items()}

    return get_metadata


GetThingStates = Annotated[
    Callable[[], Mapping[str, Any]], Depends(thing_states_getter)
]
"""A ready-made FastAPI dependency, returning a function to collect metadata.

This calls `.thing_states_getter` to provide a function that supplies a
dictionary of metadata. It describes the state of all `.Thing` instances on
the current `.ThingServer` as reported by their ``thing_state`` property.

Use this wherever you need to collect summary metadata to embed in data
files.
"""
