from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Optional
from fastapi import FastAPI
from .descriptors import ActionDescriptor, PropertyDescriptor
from .thing_description import ThingDescription
from .utilities import class_attributes

if TYPE_CHECKING:
    from .thing_server import ThingServer
    from .actions import ActionManager
class Thing:
    def attach_to_server(self, server: ThingServer, path: str):
        """Add HTTP handlers to an app for all Interaction Affordances"""
        self.path = path
        self.action_manager: ActionManager = server.action_manager

        for item in class_attributes(self):
            try:
                item.add_to_fastapi(server.app, self)
            except AttributeError:
                # We try to add everything, and ignore whatever doesn't have
                # an `add_to_fastapi` method.
                # TODO: Do we want to be more choosy about what we add?
                pass

        server.app.get(self.path)(self.thing_description)

    _cached_thing_description: Optional[tuple[str, ThingDescription]] = None
    def thing_description(self, path: Optional[str] = None) -> ThingDescription:
        """A w3c Thing Description representing this thing"""
        path = path or self.path
        if self._cached_thing_description and self._cached_thing_description[0] == path:
            return self._cached_thing_description[1]
        
        properties = []
        #actions = []
        for item in class_attributes(self):
            if isinstance(item, PropertyDescriptor):
                properties.append(item.property_affordance(self, path))
            #if isinstance(item, ActionDescriptor):
            #    actions.append(item.action_affordance(self, path))

        return ThingDescription(
            properties=properties
        )
        