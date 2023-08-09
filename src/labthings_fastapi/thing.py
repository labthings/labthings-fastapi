"""
The `Thing` class enables most of the functionality of this library,
and is the way in to most of its features. In the future, we might
support a stub version of the class in a separate package, so
that instrument control libraries can be LabThings compatible 
without a hard dependency on LabThings. But that is something we
will do in the future...
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Optional
from fastapi.encoders import jsonable_encoder
from anyio.abc import ObjectSendStream
from .descriptors import ActionDescriptor, PropertyDescriptor
from .utilities.w3c_td_model import ThingDescription, NoSecurityScheme
from .utilities import class_attributes
from .utilities.validate_thing_description import (
    validate_thing_description as utils_validate_td
)
from .utilities.introspection import get_summary, get_docstring
from .websockets import websocket_endpoint, WebSocket

if TYPE_CHECKING:
    from .thing_server import ThingServer
    from .actions import ActionManager
class Thing:
    title: str

    def attach_to_server(self, server: ThingServer, path: str):
        """Add HTTP handlers to an app for all Interaction Affordances"""
        self.path = path
        self.action_manager: ActionManager = server.action_manager

        for _name, item in class_attributes(self):
            try:
                item.add_to_fastapi(server.app, self)
            except AttributeError:
                # We try to add everything, and ignore whatever doesn't have
                # an `add_to_fastapi` method.
                # TODO: Do we want to be more choosy about what we add?
                pass

        @server.app.get(
                self.path, 
                summary=get_summary(self.thing_description),
                description=get_docstring(self.thing_description)
            )
        def thing_description():
            return self.thing_description_dict()
        
        @server.app.websocket(self.path + "ws")
        async def websocket(ws: WebSocket):
            await websocket_endpoint(self, ws)


    def validate_thing_description(self):
        """Raise an exception if the thing description is not valid"""
        td = self.thing_description_dict()
        return utils_validate_td(td)

    _cached_thing_description: Optional[tuple[str, ThingDescription]] = None
    def thing_description(self, path: Optional[str] = None) -> ThingDescription:
        """A w3c Thing Description representing this thing
        
        The w3c Web of Things working group defined a standard representation
        of a Thing, which provides a high-level description of the actions,
        properties, and events that it exposes. This endpoint delivers a JSON
        representation of the Thing Description for this Thing.
        """
        path = path or getattr(self, "path", "{base_uri}")
        if self._cached_thing_description and self._cached_thing_description[0] == path:
            return self._cached_thing_description[1]
        
        properties = {}
        actions = {}
        for name, item in class_attributes(self):
            if isinstance(item, PropertyDescriptor):
                properties[name] = item.property_affordance(self, path)
            if isinstance(item, ActionDescriptor):
                actions[name] = (item.action_affordance(self, path))

        return ThingDescription(
            title=getattr(self, "title", self.__class__.__name__),
            properties=properties,
            actions=actions,
            security="no_security",
            securityDefinitions={"no_security": NoSecurityScheme()},
        )
    
    def thing_description_dict(self, path: Optional[str] = None) -> dict:
        """A w3c Thing Description representing this thing, as a simple dict
        
        The w3c Web of Things working group defined a standard representation
        of a Thing, which provides a high-level description of the actions,
        properties, and events that it exposes. This endpoint delivers a JSON
        representation of the Thing Description for this Thing.
        """
        td: ThingDescription = self.thing_description(path=path)
        td_dict: dict = td.model_dump(exclude_none=True, by_alias=True)
        return jsonable_encoder(td_dict)

    def observe_property(self, property_name: str, stream: ObjectSendStream):
        """Register a stream to receive property change notifications"""
        prop = getattr(self.__class__, property_name)
        if not isinstance(prop, PropertyDescriptor):
            raise KeyError(f"{property_name} is not a LabThings Property")
        prop._observers_set(self).add(stream)