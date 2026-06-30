"""Code to access `~lt.Thing` features over HTTP.

This module defines a base class for controlling LabThings-FastAPI over HTTP.
It is based on `httpx`, and attempts to create a simple wrapper such that
each Action becomes a method and each Property becomes an attribute.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, Generic, Optional, TypeVar
from urllib.parse import urljoin, urlparse

import httpx
from pydantic import BaseModel, RootModel, TypeAdapter, ValidationError

from labthings_fastapi.base_descriptor import FieldTypedBaseDescriptor
from labthings_fastapi.code_generation import generate_client_class
from labthings_fastapi.exceptions import (
    ClientPropertyError,
    FailedToInvokeActionError,
    GlobalLockBusyError,
    InvocationCancelledError,
    ServerActionError,
)
from labthings_fastapi.outputs.blob import Blob, RemoteBlobData
from labthings_fastapi.problem_details import ProblemDetails, docs_url
from labthings_fastapi.thing_description._model import ThingDescription

__all__ = ["ThingClient", "poll_invocation"]
ACTION_RUNNING_KEYWORDS = ["idle", "pending", "running"]


def _optional() -> Any:
    """Return `...` to signify an unspecified default.

    This function returns `...` but is typed as `Any` so that it
    may be used as a Pydantic default factory when we don't ever
    want to see the default value.

    :returns: `...` as a sentinel for a missing value.
    """
    return ...


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
    :raises ServerActionError: if an HTTP error is found during polling.
    :return: the completed invocation as a dictionary.
    """
    first_time = True
    while invocation["status"] in ACTION_RUNNING_KEYWORDS:
        time.sleep(first_interval if first_time else interval)
        response = client.get(invocation_href(invocation))
        if response.is_error:
            try:
                message = response.json()["detail"]
            except KeyError:
                message = response.text
            raise ServerActionError(
                f"The server returned error {response.status_code} while polling "
                f"action '{invocation['action']}' with id '{invocation['id']}'. "
                f"The error message was:\n{message}."
            )
        invocation = response.json()
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
            detail = response.json().get("detail", None)
            err_msg = "Unknown error"
            if isinstance(detail, str):
                err_msg = detail
            elif (
                isinstance(detail, list) and len(detail) and isinstance(detail[0], dict)
            ):
                err_msg = detail[0].get("msg", "Unknown error")

            raise ClientPropertyError(f"Failed to set property {path}: {err_msg}")

    def invoke_action(self, path: str, **kwargs: Any) -> Any:  # noqa: DOC503
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
        :raise GlobalLockBusyError: if the action fails because of the global lock.
        :raise InvocationCancelledError: if the action is cancelled.
        """
        # weed out parameters that are `...`: these should not be sent, so that
        # the server fills in its defaults.
        payload = {}
        for key, value in kwargs.items():
            if value is ...:
                # Items that are `...` should not be included
                continue
            elif hasattr(value, "__get_pydantic_core_schema__") and not isinstance(
                value, BaseModel
            ):
                # For "pydantic-compatible" custom types, we wrap them in a
                # root model, so that they're serialised using the metadata
                # attached to the type.
                # This is important for `Blob` instances, for example.
                # Note that `RootModel` accepts expressions and variables in its
                # square brackets, hence the type: ignore.
                payload[key] = RootModel[type(value)](value)  # type: ignore[misc,operator]
            else:
                # For now, we assume all other types will serialise OK
                payload[key] = value
        # The next line uses pydantic to serialise any models to simple types.
        # We may in future serialise straight to JSON.
        plain_payload = TypeAdapter(dict).dump_python(payload, exclude_unset=True)
        response = self.client.post(urljoin(self.path, path), json=plain_payload)
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
                return Blob(
                    RemoteBlobData(
                        media_type=invocation["output"]["media_type"],
                        href=invocation["output"]["href"],
                        client=self.client,
                    )
                )
            return invocation["output"]
        # Note that flake8 is confused by the error below - this is why we ignore
        # error DOC503 for this function.
        raise _invocation_error(invocation)

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
    def from_url(
        cls, thing_url: str, client: Optional[httpx.Client] = None
    ) -> ThingClient:
        """Create a ThingClient from a URL.

        This will dynamically create a subclass with properties and actions,
        and return an instance of that subclass pointing at the Thing URL.

        :param thing_url: The base URL of the Thing, which should also be the
            URL of its Thing Description.
        :param client: is an optional `httpx.Client` object. If not present,
            one will be created. This is particularly useful if you need to
            set HTTP options, or if you want to work with a local server
            object for testing purposes (see `fastapi.TestClient`).

        :return: a `~lt.ThingClient` subclass with properties and methods that
            match the retrieved Thing Description (see :ref:`wot_thing`).
        """
        td_client = client or httpx.Client()
        r = td_client.get(thing_url)
        r.raise_for_status()
        subclass = cls.subclass_from_td(r.json())
        return subclass(thing_url, client=client)

    @classmethod
    def subclass_from_td(cls, thing_description: dict) -> type[ThingClient]:
        """Create a ThingClient subclass from a Thing Description.

        Dynamically subclass `~lt.ThingClient` to add properties and
        methods for each property and action in the Thing Description.

        :param thing_description: A :ref:`wot_td` as a dictionary, which will
            be used to construct the class.

        :return: a `~lt.ThingClient` subclass with the right properties and
            methods.
        """
        parsed_td = ThingDescription.model_validate(thing_description)
        client_cls = generate_client_class(parsed_td)
        return client_cls


Value = TypeVar("Value")


class ClientProperty(Generic[Value], FieldTypedBaseDescriptor[ThingClient, Value]):
    """A descriptor to make properties of ThingClient objects work."""

    def __init__(
        self,
        read_only: bool = False,
        write_only: bool = False,
    ) -> None:
        """Initialise a ClientProperty.

        :param read_only: whether the property should be read-only.
        :param write_only: whether the property should be write-only.
        """
        super().__init__()
        self.read_only = read_only
        self.write_only = write_only

    def instance_get(self, obj: ThingClient) -> Value:
        """Retrieve the property.

        :param obj: the client object on which the property is accessed.
        :return: the value of the property.
        :raises ClientPropertyError: if the property is write-only.
        """
        if self.write_only:
            raise ClientPropertyError("This property may not be read.")
        return obj.get_property(self.name)

    def __set__(self, obj: ThingClient, value: Value) -> None:
        """Retrieve the property.

        :param obj: the client object on which the property is set.
        :param value: the new value for the property.
        :raises ClientPropertyError: if the property is read-only.
        """
        if self.read_only:
            raise ClientPropertyError("This property may not be set.")
        return obj.set_property(self.name, value)


def client_property(read_only: bool = False, write_only: bool = False) -> Any:
    r"""Create a `ClientProperty` descriptor.

    This function returns a `ClientProperty` and passes all parameters directly
    to the constructor. It's typed as `Any` so that we can use it as a field-style
    placeholder just like `lt.property`\ .

    :param read_only: whether the property is read only.
    :param write_only: whether the property is write only.
    :return: a `ClientProperty` descriptor.
    """
    return ClientProperty(read_only=read_only, write_only=write_only)


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


def _invocation_error(invocation: Mapping[str, Any]) -> BaseException:
    """Format an error for ThingClient to raise if an invocation ends in and error.

    :param invocation: The invocation dictionary returned.
    :return: The message for the raised error
    """
    inv_id = invocation["id"]
    action_name = invocation["action"].split("/")[-1]

    err_message = "Unknown error"
    log = invocation.get("log", [])
    last_log = log[-1] if log else None
    traceback: str | None = None

    # If there's a log item, use the traceback and possibly the message.
    # we don't currently check if this message actually is an error.
    # We'll overwrite the message later, if "error" is populated.
    if last_log:
        err_message = last_log.get("message", err_message)

        exception_type = last_log.get("exception_type")
        if exception_type is not None:
            err_message = f"[{exception_type}]: {err_message}"

        # If there's a traceback, put it i
        traceback = last_log.get("traceback")

    # If there's an error specified, use that in preference to the message
    # extracted from the logs.
    try:
        pd = ProblemDetails.model_validate(invocation.get("error", None))
        if pd.type == docs_url(GlobalLockBusyError):
            # GlobalLockBusyError is worth handling specially: it's likely to
            # happen quite a bit, and "we couldn't start the action because
            # we were busy" feels like it doesn't want to be lumped in with
            # other failures.
            return GlobalLockBusyError(pd.detail)
        if pd.type == docs_url(InvocationCancelledError):
            # Similarly, InvocationCancelledError means the action was cancelled,
            # so it feels right to raise this instead
            return InvocationCancelledError(pd.detail)
        if pd.detail:
            err_message = pd.detail
        if pd.title:
            err_message = f"[{pd.title}]: {err_message}"
    except ValidationError:
        pass  # If it's not a valid problem details object, ignore it and move on.

    # Append the server traceback, if we have one.
    if traceback is not None:
        err_message += "\n\nSERVER TRACEBACK START:\n\n"
        err_message += traceback
        err_message += "\n\nSERVER TRACEBACK END\n\n"
    return ServerActionError(
        f"Action {action_name} (ID: {inv_id}) failed with error:\n{err_message}"
    )
