"""A first pass at a client library for LabThings-FastAPI

This will become its own package if it's any good. The goal is to see if we can
make a client library that produces introspectable Python objects from a Thing
Description.
"""

from __future__ import annotations
import time
from typing import Any, Optional, Union
from typing_extensions import Self  # 3.9, 3.10 compatibility
from collections.abc import Mapping
import httpx
from urllib.parse import urlparse, urljoin

from pydantic import BaseModel

from .outputs import ClientBlobOutput


ACTION_RUNNING_KEYWORDS = ["idle", "pending", "running"]


def get_link(obj: dict, rel: str) -> Mapping:
    """Retrieve a link from an object's `links` list, by its `rel` attribute"""
    return next(link for link in obj["links"] if link["rel"] == rel)


def get_link_href(obj: dict, rel: str) -> str:
    """Retrieve the `href` from an object's `links` list, by its `rel` attribute"""
    return get_link(obj, rel)["href"]


def task_href(t):
    """Extract the endpoint address from a task dictionary"""
    return get_link(t, "self")["href"]


def poll_task(client, task, interval=0.5, first_interval=0.05):
    """Poll a task until it finishes, and return the return value"""
    first_time = True
    while task["status"] in ACTION_RUNNING_KEYWORDS:
        time.sleep(first_interval if first_time else interval)
        r = client.get(task_href(task))
        r.raise_for_status()
        task = r.json()
        first_time = False
    return task


class ThingClient:
    """A client for a LabThings-FastAPI Thing

    NB ThingClient must be subclassed to add actions/properties,
    so this class will be minimally useful on its own.
    """

    def __init__(self, base_url: str, client: Optional[httpx.Client] = None):
        parsed = urlparse(base_url)
        server = f"{parsed.scheme}://{parsed.netloc}"
        self.server = server
        self.path = parsed.path
        self.client = client or httpx.Client(base_url=server)

    def get_property(self, path: str) -> Any:
        r = self.client.get(urljoin(self.path, path))
        r.raise_for_status()
        return r.json()

    def set_property(self, path: str, value: Any):
        r = self.client.put(urljoin(self.path, path), json=value)
        r.raise_for_status()

    def invoke_action(self, path: str, **kwargs):
        r = self.client.post(urljoin(self.path, path), json=kwargs)
        r.raise_for_status()
        task = poll_task(self.client, r.json())
        if task["status"] == "completed":
            if (
                isinstance(task["output"], Mapping)
                and "href" in task["output"]
                and "media_type" in task["output"]
            ):
                return ClientBlobOutput(
                    media_type=task["output"]["media_type"],
                    href=task["output"]["href"],
                    client=self.client,
                )
            return task["output"]
        else:
            raise RuntimeError(f"Action did not complete successfully: {task}")

    def follow_link(self, response: dict, rel: str) -> httpx.Response:
        """Follow a link in a response object, by its `rel` attribute"""
        href = get_link_href(response, rel)
        r = self.client.get(href)
        r.raise_for_status()
        return r

    @classmethod
    def from_url(
        cls, thing_url: str, client: Optional[httpx.Client] = None, **kwargs
    ) -> Self:
        """Create a ThingClient from a URL

        This will dynamically create a subclass with properties and actions,
        and return an instance of that subclass pointing at the Thing URL.

        Additional `kwargs` will be passed to the subclass constructor, in
        particular you may pass a `client` object (useful for testing).
        """
        td_client = client or httpx
        r = td_client.get(thing_url)
        r.raise_for_status()
        subclass = cls.subclass_from_td(r.json())
        return subclass(thing_url, client=client, **kwargs)

    @classmethod
    def subclass_from_td(cls, thing_description: dict) -> type[Self]:
        """Create a ThingClient subclass from a Thing Description"""

        class Client(cls):  # type: ignore[valid-type, misc]
            # mypy wants the superclass to be statically type-able, but
            # this isn't possible (for now) if we are to be able to
            # use this class method on `ThingClient` subclasses, i.e.
            # to provide customisation but also add methods from a
            # Thing Description.
            pass

        for name, p in thing_description["properties"].items():
            add_property(Client, name, p)
        for name, a in thing_description["actions"].items():
            add_action(Client, name, a)
        return Client


class PropertyClientDescriptor:
    pass


def property_descriptor(
    property_name: str,
    model: Union[type, BaseModel],
    description: Optional[str] = None,
    readable: bool = True,
    writeable: bool = True,
    property_path: Optional[str] = None,
) -> PropertyClientDescriptor:
    """Create a correctly-typed descriptor that gets and/or sets a property"""

    class P(PropertyClientDescriptor):
        name = property_name
        type = model
        path = property_path or property_name

    if readable:

        def __get__(
            self,
            obj: Optional[ThingClient] = None,
            _objtype: Optional[type[ThingClient]] = None,
        ):
            if obj is None:
                return self
            return obj.get_property(self.name)

        __get__.__annotations__["return"] = model
        P.__get__ = __get__  # type: ignore[attr-defined]
    if writeable:

        def __set__(self, obj: ThingClient, value: Any):
            obj.set_property(self.name, value)

        __set__.__annotations__["value"] = model
        P.__set__ = __set__  # type: ignore[attr-defined]
    if description:
        P.__doc__ = description
    return P()


def add_action(cls: type[ThingClient], action_name: str, action: dict):
    """Add an action to a ThingClient subclass"""

    def action_method(self, **kwargs):
        return self.invoke_action(action_name, **kwargs)

    if "output" in action and "type" in action["output"]:
        action_method.__annotations__["return"] = action["output"]["type"]
    if "description" in action:
        action_method.__doc__ = action["description"]
    setattr(cls, action_name, action_method)


def add_property(cls: type[ThingClient], property_name: str, property: dict):
    """Add a property to a ThingClient subclass"""
    setattr(
        cls,
        property_name,
        property_descriptor(
            property_name,
            property.get("type", Any),
            description=property.get("description", None),
            writeable=not property.get("readOnly", False),
            readable=not property.get("writeOnly", False),
        ),
    )
