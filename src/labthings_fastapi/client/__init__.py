"""Code to access `.Thing` features over HTTP.

This module defines a base class for controlling LabThings-FastAPI over HTTP.
It is based on `httpx`, and attempts to create a simple wrapper such that
each Action becomes a method and each Property becomes an attribute.
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
from ..exceptions import (
    FailedToInvokeActionError,
    ServerActionError,
    ClientPropertyError,
)

__all__ = ["ThingClient", "poll_invocation"]
ACTION_RUNNING_KEYWORDS = ["idle", "pending", "running"]


class ObjectHasNoLinksError(KeyError):
    """We attempted to use the `links` key but it was not there.

    `links` is used in several places, including in the representation of
    `.Invocation` objects. It should be a list of dictionaries, each of
    which represents a link, with `href` and `rel` keys.
    """


def _get_link(obj: dict, rel: str) -> Mapping:
    """Retrieve a link from an object's ``links`` list, by its ``rel`` attribute.

    Various places in the :ref:`wot_td` feature a list of links. This is represented
    in JSON as a property called ``links`` which is a list of objects that have
    ``href`` and ``rel`` properties.

    This function takes an object (which deserialises to a ``dict`` in Python)
    and looks for its ``links`` item, then iterates through the objects there
    to find the first one with a particular ``rel`` value. For example, we
    use this to find the ``self`` link on an invocation.

    :param obj: the deserialised JSON response from querying an invocation.
        this should be a dictionary containing at least a ``links`` key, which
        is a list of dictionaries, each with ``href`` and ``rel`` defined.
    :param rel: the value of the ``rel`` key in the link we are looking for.

    :return: a dictionary representing the link. It should contain at least
        ``href`` and ``rel`` keys.

    :raise ObjectHasNoLinksError: if there is no ``links`` item.
    :raise KeyError: if there is no link with the specified ``rel`` value.
    """
    if "links" not in obj:
        raise ObjectHasNoLinksError(f"Can't find any links on {obj}.")
    try:
        return next(link for link in obj["links"] if link["rel"] == rel)
    except StopIteration as e:
        raise KeyError(f"No link was found with rel='{rel}' on {obj}.") from e


def invocation_href(invocation: dict) -> str:
    """Extract the endpoint address from an invocation dictionary.

    :param invocation: The invocation's dictionary representation, i.e. the
        deserialised JSON response from starting or polling an action.

    :return: The `href` value to poll the invocation.

    .. note::

        Exceptions may propagate from `._get_link`.
    """
    return _get_link(invocation, "self")["href"]


def poll_invocation(
    client: httpx.Client,
    invocation: dict,
    interval: float = 0.5,
    first_interval: float = 0.05,
) -> dict:
    """Poll a invocation until it finishes, and return the output.

    When actions are invoked in a LabThings-FastAPI server, the
    initial POST request returns immediately. The returned invocation
    includes a link that may be polled to find out when the action
    has completed, whether it was successful, and retrieve its
    output.

    :param client: the `httpx.Client` to use for HTTP requests.
    :param invocation: the dictionary returned from the initial POST request.
    :param interval: sets how frequently we poll, in seconds.
    :param first_interval: sets how long we wait before the first
        polling request. Often, it makes sense for this to be a short
        interval, in case the action fails (or returns) immediately.

    :return: the completed invocation as a dictionary.
    """
    first_time = True
    while invocation["status"] in ACTION_RUNNING_KEYWORDS:
        time.sleep(first_interval if first_time else interval)
        r = client.get(invocation_href(invocation))
        r.raise_for_status()
        invocation = r.json()
        first_time = False
    return invocation


class ThingClient:
    """A client for a LabThings-FastAPI Thing.

    .. note::
        ThingClient must be subclassed to add actions/properties,
        so this class will be minimally useful on its own.

        The best way to get a client for a particular Thing is
        currently `.ThingClient.from_url`, which dynamically
        creates a subclass with the right attributes.
    """

    def __init__(self, base_url: str, client: Optional[httpx.Client] = None) -> None:
        """Create a ThingClient connected to a remote Thing.

        :param base_url: the base URL of the Thing. This should be the URL
            of the Thing Description document.
        :param client: an optional `httpx.Client` object to use for all
            HTTP requests. This may be a `fastapi.TestClient` object for
            testing purposes.
        """
        parsed = urlparse(base_url)
        server = f"{parsed.scheme}://{parsed.netloc}"
        self.server = server
        self.path = parsed.path
        self.client = client or httpx.Client(base_url=server)

    def get_property(self, path: str) -> Any:
        """Make a GET request to retrieve the value of a property.

        :param path: the URI of the ``getproperty`` endpoint, relative
            to the ``base_url``.

        :return: the property's value, as deserialised from JSON.
        :raise ClientPropertyError: is raised the property cannot be read.
        """
        response = self.client.get(urljoin(self.path, path))
        if response.is_error:
            detail = response.json().get("detail")
            err_msg = "Unknown error"
            if isinstance(detail, str):
                err_msg = detail
            raise ClientPropertyError(f"Failed to get property {path}: {err_msg}")

        return response.json()

    def set_property(self, path: str, value: Any) -> None:
        """Make a PUT request to set the value of a property.

        :param path: the URI of the ``getproperty`` endpoint, relative
            to the ``base_url``.
        :param value: the property's value. Currently this must be
            serialisable to JSON.
        :raise ClientPropertyError: is raised the property cannot be set.
        """
        response = self.client.put(urljoin(self.path, path), json=value)
        if response.is_error:
            detail = response.json().get("detail")
            err_msg = "Unknown error"
            if isinstance(detail, str):
                err_msg = detail
            elif (
                isinstance(detail, list) and len(detail) and isinstance(detail[0], dict)
            ):
                err_msg = detail[0].get("msg", "Unknown error")

            raise ClientPropertyError(f"Failed to get property {path}: {err_msg}")

    def invoke_action(self, path: str, **kwargs: Any) -> Any:
        r"""Invoke an action on the Thing.

        This method will make the initial POST request to invoke an action,
        then poll the resulting invocation until it completes. If successful,
        the action's output will be returned directly.

        While the action is running, log messages will be re-logged locally.
        If you have enabled logging to the console, these should be visible.

        :param path: the URI of the ``invokeaction`` endpoint, relative to the
            ``base_url``
        :param \**kwargs: Additional arguments will be combined into the JSON
            body of the ``POST`` request and sent as input to the action.
            These will be validated on the server.

        :return: the output value of the action.

        :raise FailedToInvokeActionError: if the action fails to start.
        :raise ServerActionError: is raised if the action does not complete
            successfully.
        """
        for k in kwargs.keys():
            value = kwargs[k]
            if isinstance(value, ClientBlobOutput):
                # ClientBlobOutput objects may be used as input to a subsequent
                # action. When this is done, they should be serialised to a dict
                # with `href` and `media_type` keys, as done below.
                # Ideally this should be replaced with `Blob` and the use of
                # `pydantic` models to serialise action inputs.
                #
                # Note that the blob will not be uploaded: we rely on the blob
                # still existing on the server.
                kwargs[k] = {"href": value.href, "media_type": value.media_type}
        response = self.client.post(urljoin(self.path, path), json=kwargs)
        if response.is_error:
            message = _construct_failed_to_invoke_message(path, response)
            raise FailedToInvokeActionError(message)

        invocation = poll_invocation(self.client, response.json())
        if invocation["status"] == "completed":
            if (
                isinstance(invocation["output"], Mapping)
                and "href" in invocation["output"]
                and "media_type" in invocation["output"]
            ):
                return ClientBlobOutput(
                    media_type=invocation["output"]["media_type"],
                    href=invocation["output"]["href"],
                    client=self.client,
                )
            return invocation["output"]
        message = _construct_invocation_error_message(invocation)
        raise ServerActionError(message)

    def follow_link(self, response: dict, rel: str) -> httpx.Response:
        """Follow a link in a response object, by its `rel` attribute.

        :param response: is the dictionary returned by e.g. `.poll_invocation`.
        :param rel: picks the link to follow by matching its ``rel``
            item.

        :return: the response to making a ``GET`` request to the link.
        """
        href = _get_link(response, rel)["href"]
        r = self.client.get(href)
        r.raise_for_status()
        return r

    @classmethod
    def from_url(cls, thing_url: str, client: Optional[httpx.Client] = None) -> Self:
        """Create a ThingClient from a URL.

        This will dynamically create a subclass with properties and actions,
        and return an instance of that subclass pointing at the Thing URL.

        :param thing_url: The base URL of the Thing, which should also be the
            URL of its Thing Description.
        :param client: is an optional `httpx.Client` object. If not present,
            one will be created. This is particularly useful if you need to
            set HTTP options, or if you want to work with a local server
            object for testing purposes (see `fastapi.TestClient`).

        :return: a `.ThingClient` subclass with properties and methods that
            match the retrieved Thing Description (see :ref:`wot_thing`).
        """
        td_client = client or httpx
        r = td_client.get(thing_url)
        r.raise_for_status()
        subclass = cls.subclass_from_td(r.json())
        return subclass(thing_url, client=client)

    @classmethod
    def subclass_from_td(cls, thing_description: dict) -> type[Self]:
        """Create a ThingClient subclass from a Thing Description.

        Dynamically subclass `.ThingClient` to add properties and
        methods for each property and action in the Thing Description.

        :param thing_description: A :ref:`wot_td` as a dictionary, which will
            be used to construct the class.

        :return: a `.ThingClient` subclass with the right properties and
            methods.
        """
        my_thing_description = thing_description

        class Client(cls):  # type: ignore[valid-type, misc]
            # mypy wants the superclass to be statically type-able, but
            # this isn't possible (for now) if we are to be able to
            # use this class method on `ThingClient` subclasses, i.e.
            # to provide customisation but also add methods from a
            # Thing Description.
            thing_description = my_thing_description

        for name, p in thing_description["properties"].items():
            add_property(Client, name, p)
        for name, a in thing_description["actions"].items():
            add_action(Client, name, a)
        return Client


class PropertyClientDescriptor:
    """A base class for properties on `.ThingClient` objects."""

    name: str
    type: type | BaseModel
    path: str


def property_descriptor(
    property_name: str,
    model: Union[type, BaseModel],
    description: Optional[str] = None,
    readable: bool = True,
    writeable: bool = True,
    property_path: Optional[str] = None,
) -> PropertyClientDescriptor:
    """Create a correctly-typed descriptor that gets and/or sets a property.

    The returned `.PropertyClientDescriptor` will have ``__get__`` and
    (optionally) ``__set__`` methods that are typed according to the
    supplied ``model``. The descriptor should be added to a `.ThingClient`
    subclass and used to access the relevant property via
    `.ThingClient.get_property` and `.ThingClient.set_property`.

    :param property_name: should be the name of the property (i.e. the
        name it takes in the thing description, and also the name it is
        assigned to in the class).
    :param model: the Python ``type`` or a ``pydantic.BaseModel`` that
        represents the datatype of the property.
    :param description: text to use for a docstring.
    :param readable: whether the property may be read (i.e. has ``__get__``).
    :param writeable: whether the property may be written to.
    :param property_path: the URL of the ``getproperty`` and ``setproperty``
        HTTP endpoints. Currently these must both be the same. These are
        relative to the ``base_url``, i.e. the URL of the Thing Description.

    :return: a descriptor allowing access to the specified property.
    """

    class P(PropertyClientDescriptor):
        name = property_name
        type = model
        path = property_path or property_name

    if readable:

        def __get__(
            self: PropertyClientDescriptor,
            obj: Optional[ThingClient] = None,
            _objtype: Optional[type[ThingClient]] = None,
        ) -> Any:
            if obj is None:
                return self
            return obj.get_property(self.name)

        __get__.__annotations__["return"] = model
        P.__get__ = __get__  # type: ignore[attr-defined]
    if writeable:

        def __set__(
            self: PropertyClientDescriptor, obj: ThingClient, value: Any
        ) -> None:
            obj.set_property(self.name, value)

        __set__.__annotations__["value"] = model
        P.__set__ = __set__  # type: ignore[attr-defined]
    if description:
        P.__doc__ = description
    return P()


def add_action(cls: type[ThingClient], action_name: str, action: dict) -> None:
    """Add an action to a ThingClient subclass.

    A method will be added to the class that calls the provided action.
    Currently, this will have a return type hint but no argument names
    or type hints.

    :param cls: the `.ThingClient` subclass to which we are adding the
        action.
    :param action_name: is both the name we assign the method to, and
        the name of the action in the Thing Description.
    :param action: a dictionary representing the action, in :ref:`wot_td`
        format.
    """

    def action_method(self: ThingClient, **kwargs: Any) -> Any:
        return self.invoke_action(action_name, **kwargs)

    if "output" in action and "type" in action["output"]:
        action_method.__annotations__["return"] = action["output"]["type"]
    if "description" in action:
        action_method.__doc__ = action["description"]
    setattr(cls, action_name, action_method)


def add_property(cls: type[ThingClient], property_name: str, property: dict) -> None:
    """Add a property to a ThingClient subclass.

    A descriptor will be added to the provided class that makes the
    attribute ``property_name`` get and/or set the property described
    by the ``property`` dictionary.


    :param cls: the `.ThingClient` subclass to which we are adding the
        property.
    :param property_name: is both the name we assign the descriptor to, and
        the name of the property in the Thing Description.
    :param property: a dictionary representing the property, in :ref:`wot_td`
        format.
    """
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


def _construct_failed_to_invoke_message(path: str, response: httpx.Response) -> str:
    """Format an error for ThingClient to raise if an invocation fails to start.

    :param path: The path of the action
    :param response: The response object from the POST request to start the action.
    :return: The message for the raised error
    """
    # Default message if we can't process return
    message = f"Unknown error when invoking action {path}"
    details = response.json().get("detail", [])

    if isinstance(details, str):
        message = f"Error when invoking action {path}: {details}"
    if isinstance(details, list) and len(details) and isinstance(details[0], dict):
        loc = details[0].get("loc", [])
        loc_str = "" if len(loc) < 2 else f"'{loc[1]}' - "
        err_msg = details[0].get("msg", "Unknown Error")
        message = f"Error when invoking action {path}: {loc_str}{err_msg}"
    return message


def _construct_invocation_error_message(invocation: Mapping[str, Any]) -> str:
    """Format an error for ThingClient to raise if an invocation ends in and error.

    :param invocation: The invocation dictionary returned.
    :return: The message for the raised error
    """
    inv_id = invocation["id"]
    action_name = invocation["action"].split("/")[-1]

    err_message = "Unknown error"

    if len(invocation.get("log", [])) > 0:
        last_log = invocation["log"][-1]
        err_message = last_log.get("message", err_message)

        exception_type = last_log.get("exception_type")
        if exception_type is not None:
            err_message = f"[{exception_type}]: {err_message}"

        traceback = last_log.get("traceback")
        if traceback is not None:
            err_message += "\n\nSERVER TRACEBACK START:\n\n"
            err_message += traceback
            err_message += "\n\nSERVER TRACEBACK END\n\n"

    return f"Action {action_name} (ID: {inv_id}) failed with error:\n{err_message}"
