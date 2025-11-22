"""Add a FastAPI endpoint without making it an action.

The `.EndpointDescriptor` wraps a function and marks it to be added to the
HTTP API at the same time as the properties and actions of the host `.Thing`.
This is intended to allow flexibility to implement endpoints that cannot be
described in a Thing Description as actions or properties.

It may use any `fastapi` responses or arguments, as it passes keyword
arguments through to the relevant `fastapi` decorator.

This will most usually be applied as a decorator with arguments, available
as :deco:`.fastapi_endpoint`. See the documentation for that function for
more detail.
"""

from __future__ import annotations
from functools import partial, wraps

from .base_descriptor import BaseDescriptor
from .exceptions import NotConnectedToServerError
from .utilities.introspection import get_docstring

from typing import (
    Any,
    Callable,
    Literal,
    Mapping,
    Optional,
    TYPE_CHECKING,
)
from fastapi import FastAPI

if TYPE_CHECKING:
    from .thing import Thing

HTTPMethod = Literal["get", "post", "put", "delete"]
"""Valid HTTP verbs to use with `.fastapi_endpoint` or `.EndpointDescriptor`."""


class EndpointDescriptor(BaseDescriptor):
    """A descriptor to allow Things to easily add other endpoints."""

    def __init__(
        self,
        func: Callable,
        http_method: HTTPMethod = "get",
        path: Optional[str] = None,
        **kwargs: Mapping[str, Any],
    ) -> None:
        r"""Initialise an EndpointDescriptor.

        See `.fastapi_endpoint`, which is the usual way of instantiating this
        class.

        :param func: is the method (defined on a `.Thing`) wrapped by this
            descriptor.
        :param http_method: the HTTP verb we are responding to. This selects
            the FastAPI decorator: ``"get"`` corresponds to ``@app.get``.
        :param path: the URL, relative to the host `.Thing`, for the endpoint.
        :param \**kwargs: additional keyword arguments are passed to the
            FastAPI decorator, allowing you to specify responses, OpenAPI
            parameters, etc.
        """
        super().__init__()
        self.func = func
        self.http_method = http_method
        self._path = path
        self.kwargs = kwargs
        self.__doc__ = get_docstring(func)

    def instance_get(self, obj: Thing) -> Callable:
        """Bind the method to the host `.Thing` and return it.

        This descriptor returns the wrapped function, with the `.Thing` bound as its
        first argument. This is the usual behaviour for Python methods.

        :param obj: The `.Thing` on which the descriptor is defined.

        :return: The wrapped function, bound to the `.Thing` (when called as
            an instance attribute).
        """
        return wraps(self.func)(partial(self.func, obj))

    @property
    def path(self) -> str:
        """The path of the endpoint (relative to the Thing)."""
        return self._path or self.name

    def add_to_fastapi(self, app: FastAPI, thing: Thing) -> None:
        """Add an endpoint for this function to a FastAPI app.

        We will add an endpoint to the app, bound to a particular `.Thing`.
        The URL will be prefixed with the `.Thing` path, i.e. the specified
        URL (which defaults to the name of this descriptor) is relative to
        the host `.Thing`.

        :param app: the `fastapi.FastAPI` application we are adding to.
        :param thing: the `.Thing` we're bound to.

        :raises NotConnectedToServerError: if there is no ``path`` attribute
            of the host `.Thing` (which usually means it is not yet connected
            to a server).
        """
        if thing.path is None:
            raise NotConnectedToServerError(
                "Attempted to add an endpoint to the API, but there is no "
                "path set on the Thing. This usually means it is not connected "
                "to a ThingServer."
            )
        # fastapi_endpoint is equivalent to app.get/app.post/whatever
        fastapi_endpoint = getattr(app, self.http_method)
        bound_function = partial(self.func, thing)
        # NB the line above can't use self.__get__ as wraps() confuses FastAPI
        kwargs: dict[str, Any] = {  # Auto-populate description and summary
            "description": f"## {self.title}\n\n {self.description}",
            "summary": self.title,
        }
        kwargs.update(self.kwargs)
        fastapi_endpoint(thing.path + self.path, **kwargs)(bound_function)


def fastapi_endpoint(
    method: HTTPMethod, path: Optional[str] = None, **kwargs: Any
) -> Callable[[Callable], EndpointDescriptor]:
    r"""Mark a function as a FastAPI endpoint without making it an action.

    This decorator will cause a method of a `.Thing` to be directly added to
    the HTTP API, bypassing the machinery underlying Action and Property
    affordances. Such endpoints will not be documented in the :ref:`wot_td` but
    may be used as the target of links. For example, this could allow a file
    to be downloaded from the `.Thing` at a known URL, or serve a video stream
    that wouldn't be supported as a `.Blob`\ .

    The majority of `.Thing` implementations won't need this decorator, but
    it is here to enable flexibility when it's needed.

    This decorator always takes arguments; in particular, ``method`` is
    required. It should be used as:

    .. code-block:: python

        class DownloadThing(Thing):
            @fastapi_endpoint("get")
            def plain_text_response(self) -> str:
                return "example string"

    This decorator is intended to work very similarly to the `fastapi` decorators
    ``@app.get``, ``@app.post``, etc., with two changes:

    1. The path is relative to the host `.Thing` and will default to the name
        of the method.
    2. The method will be called with the host `.Thing` as its first argument,
        i.e. it will be bound to the class as usua.

    :param method: The HTTP verb this endpoint responds to.
    :param path: The path, relative to the host `.Thing` base URL.
    :param \**kwargs: Additional keyword arguments are passed to the
        `fastapi.FastAPI.get` decorator if ``method`` is ``get``, or to
        the equivalent decorator for other HTTP verbs.

    :return: When used as intended, the result is an `.EndpointDescriptor`.
    """

    def decorator(func: Callable) -> EndpointDescriptor:
        return EndpointDescriptor(func, http_method=method, path=path, **kwargs)

    return decorator
