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
from collections.abc import Mapping
from fastapi.encoders import jsonable_encoder
from fastapi import Request
from anyio.abc import ObjectSendStream
from anyio.from_thread import BlockingPortal
from anyio.to_thread import run_sync
from .descriptors import PropertyDescriptor, ActionDescriptor
from .thing_description.model import ThingDescription, NoSecurityScheme
from .utilities import class_attributes
from .thing_description import validation
from .utilities.introspection import get_summary, get_docstring
from .websockets import websocket_endpoint, WebSocket
from .thing_settings import ThingSettings

if TYPE_CHECKING:
    from .server import ThingServer
    from .actions import ActionManager


class Thing:
    """Represents a Thing, as defined by the Web of Things standard.

    This class should encapsulate the code that runs a piece of hardware, or provides
    a particular function - it will correspond to a path on the server, and a Thing
    Description document.

    Your Thing should be a subclass of Thing - note that we don't define `__init__` so
    you are free to initialise as you like and don't need to call `super().__init__`.

    ## Subclassing Notes

    * `__init__`: You should accept any arguments you need to configure the Thing
      in `__init__`. Don't initialise any hardware at this time, as your Thing may
      be instantiated quite early, or even at import time.
    * `__enter__(self)` and `__exit__(self, exc_t, exc_v, exc_tb)` are where you
      should start and stop communications with the hardware. This is Python's standard
      "context manager" protocol. The arguments of `__exit__` will be `None` unless
      an exception has occurred. You should be safe to ignore them, and just include
      code that will close down your hardware. It's equivalent to a `finally:` block.
    * Properties and Actions are defined using decorators: the `@thing_action` decorator
      declares a method to be an action, which will run when it's triggered, and the
      `@thing_property` decorator (or `PropertyDescriptor` descriptor) does the same for
      a property. See the documentation on those functions for more detail.
    * `title` will be used in various places as the human-readable name of your Thing,
      so it makes sense to set this in a subclass.

    There are various LabThings methods that you should avoid overriding unless you know
    what you are doing: anything not mentioned above that's defined in `Thing` is
    probably best left along. They may in time be collected together into a single
    object to avoid namespace clashes.
    """

    title: str
    _labthings_blocking_portal: Optional[BlockingPortal] = None
    path: Optional[str]

    async def __aenter__(self):
        """Context management is used to set up/close the thing.

        As things (currently) do everything with threaded code, we define
        async __aenter__ and __aexit__ wrappers to call the synchronous
        code, if it exists.
        """
        if hasattr(self, "__enter__"):
            return await run_sync(self.__enter__)
        else:
            return self

    async def __aexit__(self, exc_t, exc_v, exc_tb):
        """Wrap context management functions, if they exist.

        See __aenter__ docs for more details.
        """
        if hasattr(self, "__exit__"):
            return await run_sync(self.__exit__, exc_t, exc_v, exc_tb)

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
            description=get_docstring(self.thing_description),
            response_model_exclude_none=True,
            response_model_by_alias=True,
        )
        def thing_description(request: Request) -> ThingDescription:
            return self.thing_description(base=str(request.base_url))

        @server.app.websocket(self.path + "ws")
        async def websocket(ws: WebSocket):
            await websocket_endpoint(self, ws)

    _labthings_thing_settings: Optional[ThingSettings] = None

    @property
    def thing_settings(self) -> ThingSettings:
        """A dictionary that can be used to persist settings between runs"""
        if self._labthings_thing_settings is None:
            raise RuntimeError(
                "Settings may not be accessed before we are attached to the server."
            )
        return self._labthings_thing_settings

    @thing_settings.setter
    def thing_settings(self, newsettings: ThingSettings):
        self.thing_settings.replace(newsettings)

    _labthings_thing_state: Optional[dict] = None

    @property
    def thing_state(self) -> Mapping:
        """Return a dictionary summarising our current state

        This is intended to be an easy way to collect metadata from a Thing that
        summarises its state. It might be used, for example, to record metadata
        along with each reading/image/etc. when an instrument is saving data.

        It's best to populate this automatically so it can always be accessed. If
        it requires calls e.g. to a serial instrument, bear in mind it may be called
        quite often and shouldn't take too long.

        Some measure of cacheing here is a nice aim for the future, but not yet
        implemented.
        """
        if self._labthings_thing_state is None:
            self._labthings_thing_state = {}
        return self._labthings_thing_state

    def validate_thing_description(self):
        """Raise an exception if the thing description is not valid"""
        td = self.thing_description_dict()
        return validation.validate_thing_description(td)

    _cached_thing_description: Optional[
        tuple[Optional[str], Optional[str], ThingDescription]
    ] = None

    def thing_description(
        self, path: Optional[str] = None, base: Optional[str] = None
    ) -> ThingDescription:
        """A w3c Thing Description representing this thing

        The w3c Web of Things working group defined a standard representation
        of a Thing, which provides a high-level description of the actions,
        properties, and events that it exposes. This endpoint delivers a JSON
        representation of the Thing Description for this Thing.
        """
        path = path or getattr(self, "path", "{base_uri}")
        if (
            self._cached_thing_description
            and self._cached_thing_description[0] == path
            and self._cached_thing_description[1] == base
        ):
            return self._cached_thing_description[2]

        properties = {}
        actions = {}
        for name, item in class_attributes(self):
            if hasattr(item, "property_affordance"):
                properties[name] = item.property_affordance(self, path)
            if hasattr(item, "action_affordance"):
                actions[name] = item.action_affordance(self, path)

        td = ThingDescription(
            title=getattr(self, "title", self.__class__.__name__),
            properties=properties,
            actions=actions,
            security="no_security",
            securityDefinitions={"no_security": NoSecurityScheme()},
            base=base,
        )
        self._cached_thing_description = (path, base, td)
        return td

    def thing_description_dict(
        self,
        path: Optional[str] = None,
        base: Optional[str] = None,
    ) -> dict:
        """A w3c Thing Description representing this thing, as a simple dict

        The w3c Web of Things working group defined a standard representation
        of a Thing, which provides a high-level description of the actions,
        properties, and events that it exposes. This endpoint delivers a JSON
        representation of the Thing Description for this Thing.
        """
        td: ThingDescription = self.thing_description(path=path, base=base)
        td_dict: dict = td.model_dump(exclude_none=True, by_alias=True)
        return jsonable_encoder(td_dict)

    def observe_property(self, property_name: str, stream: ObjectSendStream):
        """Register a stream to receive property change notifications"""
        prop = getattr(self.__class__, property_name)
        if not isinstance(prop, PropertyDescriptor):
            raise KeyError(f"{property_name} is not a LabThings Property")
        prop._observers_set(self).add(stream)

    def observe_action(self, action_name: str, stream: ObjectSendStream):
        """Register a stream to receive action status change notifications"""
        action = getattr(self.__class__, action_name)
        if not isinstance(action, ActionDescriptor):
            raise KeyError(f"{action_name} is not an LabThings Action")
        observers = action._observers_set(self)
        observers.add(stream)
