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

from ..utilities.introspection import get_docstring, get_summary

from typing import (
    Callable,
    Literal,
    Mapping,
    Optional,
    Union,
    overload,
    TYPE_CHECKING,
)
from typing_extensions import Self  # 3.9, 3.10 compatibility
from fastapi import FastAPI

if TYPE_CHECKING:
    from ..thing import Thing

HTTPMethod = Literal["get", "post", "put", "delete"]
"""Valid HTTP verbs to use with `.fastapi_endpoint` or `.EndpointDescriptor`."""


class EndpointDescriptor:
    """A descriptor to allow Things to easily add other endpoints."""

    def __init__(
        self,
        func: Callable,
        http_method: HTTPMethod = "get",
        path: Optional[str] = None,
        **kwargs: Mapping,
    ):
        """Initialise an EndpointDescriptor.

        See `.fastapi_endpoint`, which is the usual way of instantiating this
        class.

        :param func: is the method (defined on a `.Thing`) wrapped by this
            descriptor.
        :param http_method: the HTTP verb we are responding to. This selects
            the FastAPI decorator: ``"get"`` corresponds to ``@app.get``.
        :param path: the URL, relative to the host `.Thing`, for the endpoint.
        :param **kwargs: additional keyword arguments are passed to the
            FastAPI decorator, allowing you to specify responses, OpenAPI
            parameters, etc.
        """
        self.func = func
        self.http_method = http_method
        self._path = path
        self.kwargs = kwargs

    @overload
    def __get__(self, obj: Literal[None], type=None) -> Self: ...

    @overload
    def __get__(self, obj: Thing, type=None) -> Callable: ...

    def __get__(
        self, obj: Optional[Thing], type: type[Thing] | None = None
    ) -> Union[Self, Callable]:
        """Bind the method to the host `.Thing` and return it.

        When called on a `.Thing`, this descriptor returns the wrapped
        function, with the `.Thing` bound as its first argument. This is
        the usual behaviour for Python methods.

        If `obj` is None, the descriptor is returned, so we can get
        the descriptor conveniently as an attribute of the class.

        :param obj: The `.Thing` on which the descriptor is defined, or ``None``.
        :param type: The class on which the descriptor is defined.

        :return: The wrapped function, bound to the `.Thing` (when called as
            an instance attribute), or the descriptor itself (when called as
            a class attribute).
        """
        if obj is None:
            return self
        return wraps(self.func)(partial(self.func, obj))

    @property
    def name(self):
        """The name of the wrapped function."""
        return self.func.__name__

    @property
    def path(self):
        """The path of the endpoint (relative to the Thing)."""
        return self._path or self.name

    @property
    def title(self):
        """A human-readable title."""
        return get_summary(self.func) or self.name

    @property
    def description(self):
        """A description of the endpoint."""
        return get_docstring(self.func, remove_summary=True)

    def add_to_fastapi(self, app: FastAPI, thing: Thing):
        """Add an endpoint for this function to a FastAPI app.

        We will add an endpoint to the app, bound to a particular `.Thing`.
        The URL will be prefixed with the `.Thing` path, i.e. the specified
        URL (which defaults to the name of this descriptor) is relative to
        the host `.Thing`.

        :param app: the `fastapi.FastAPI` application we are adding to.
        :param thing: the `.Thing` we're bound to.
        """
        # fastapi_endpoint is equivalent to app.get/app.post/whatever
        fastapi_endpoint = getattr(app, self.http_method)
        bound_function = partial(self.func, thing)
        # NB the line above can't use self.__get__ as wraps() confuses FastAPI
        kwargs = {  # Auto-populate description and summary
            "description": f"## {self.title}\n\n {self.description}",
            "summary": self.title,
        }
        kwargs.update(self.kwargs)
        fastapi_endpoint(thing.path + self.path, **kwargs)(bound_function)
