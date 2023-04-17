from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Optional
from fastapi import FastAPI
from .descriptors import ActionDescriptor, PropertyDescriptor
from .utilities.w3c_td_model import ThingDescription, NoSecurityScheme
from .utilities import class_attributes
from .utilities.validate_thing_description import validate_thing_description

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

        @server.app.get(self.path)
        def thing_description():
            return self.thing_description().dict(exclude_none=True)
        thing_description()  # run it once to build the model to check it works (i.e. is valid)
        

    _cached_thing_description: Optional[tuple[str, ThingDescription]] = None
    def thing_description(self, path: Optional[str] = None) -> ThingDescription:
        """A w3c Thing Description representing this thing"""
        path = path or self.path
        if self._cached_thing_description and self._cached_thing_description[0] == path:
            return self._cached_thing_description[1]
        
        properties = {}
        #actions = []
        for name, item in class_attributes(self):
            if isinstance(item, PropertyDescriptor):
                properties[name] = item.property_affordance(self, path)
            #if isinstance(item, ActionDescriptor):
            #    actions.append(item.action_affordance(self, path))

        return ThingDescription(
            title=getattr(self, "title", self.__class__.__name__),
            properties=properties,
            security="no_security",
            securityDefinitions={"no_security": NoSecurityScheme()},
        )
        