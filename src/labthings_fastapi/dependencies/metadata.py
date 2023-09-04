from __future__ import annotations
from typing import Annotated, Any
from collections.abc import Mapping

from fastapi import Depends, Request

from ..thing import Thing
from ..thing_server import find_thing_server


def get_thing_states(
            request: Request
    ) -> dict:
    """A dependency to retrieve summary metadata from all Things in this server.
    
    This is intended to make it easy for a Thing to summarise the other Things
    it's associated with, for example it's used to populate the UserComment
    EXIF field in the OpenFlexure Microscope.
    """
    server = find_thing_server(request.app)
    metadata = {k:  v.thing_state for k, v in server.things.items()}
    return metadata

ThingStates = Annotated(Mapping[str, Any], Depends(get_thing_states))
