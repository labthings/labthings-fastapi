r"""Middleware to make url_for available as a context variable.

There are several places in LabThings where we need to be able to include URLs
to other endpoints in the LabThings server, most notably in the output of
Actions. For example, if an Action outputs a `.Blob`\ , the URL to download
that `.Blob` would need to be generated.

Actions are particularly complicated, as they are often invoked by one HTTP
request, and polled by subsequent requests. In order to ensure that the URL
we generate is consistent with the URL being requested, we should always use
the ``url_for`` method from the HTTP request we are responding to. This means
it is, in general, not a great idea to generate URLs within an Action and hold
on to them as strings. While it will work most of the time, it would be better
to store the endpoint name, and only convert it to a URL when the action's
output is serialised by FastAPI.

This module includes a `.ContextVar` for the ``url_for`` function, and provides
a middleware function that sets the context variable for every request, and a
custom type that works with `pydantic` to convert endpoint names to URLs at
serialisation time.
"""

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Self
from fastapi import Request, Response
from pydantic import GetCoreSchemaHandler
from pydantic.networks import AnyUrl
from pydantic_core import core_schema
from starlette.datastructures import URL

from labthings_fastapi.exceptions import NoUrlForContextError

url_for_ctx: ContextVar[Callable[..., URL]] = ContextVar("url_for_ctx")
"""Context variable storing the url_for function for the current request."""


@contextmanager
def set_url_for_context(
    url_for_function: Callable[..., URL],
) -> Iterator[None]:
    """Set the url_for context variable for the duration of the context.

    :param url_for_function: The url_for function to set in the context variable.
    """
    token = url_for_ctx.set(url_for_function)
    try:
        yield
    finally:
        url_for_ctx.reset(token)


def dummy_url_for(endpoint: str, **params: Any) -> URL:
    r"""Generate a fake URL as a placeholder for a real ``url_for`` function.

    This is intended for use in test code.

    :param endpoint: The name of the endpoint.
    :param \**params: The path parameters.
    :return: A fake URL.
    """
    param_str = "&".join(f"{k}={v}" for k, v in params.items())
    return URL(f"urlfor://{endpoint}/?{param_str}")


def url_for(endpoint_name: str, **params: Any) -> URL:
    r"""Get a URL for the given endpoint name and path parameters.

    This function uses the ``url_for`` function stored in a context variable
    to convert endpoint names and parameters to URLs. It is intended to have
    the same signature as `fastapi.Request.url_for`\ .

    :param endpoint_name: The name of the endpoint to generate a URL for.
    :param \**params: The path parameters to use in the URL.
    :return: The generated URL.
    :raises NoUrlForContextError: if there is no url_for function in the context.
    """
    try:
        url_for_func = url_for_ctx.get()
    except LookupError as err:
        raise NoUrlForContextError("No url_for context available.") from err
    return url_for_func(endpoint_name, **params)


async def url_for_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Middleware to set the url_for context variable for each request.

    This middleware retrieves the ``url_for`` function from the incoming
    request, and sets it in the context variable for the duration of the
    request.

    :param request: The incoming FastAPI request.
    :param call_next: The next middleware or endpoint handler to call.
    :return: The response from the next handler.
    """
    token = url_for_ctx.set(request.url_for)
    try:
        response = await call_next(request)
    finally:
        url_for_ctx.reset(token)
    return response


class URLFor:
    """A pydantic-compatible type that converts endpoint names to URLs."""

    def __init__(self, endpoint_name: str, **params: Any) -> None:
        r"""Create a URLFor instance.

        :param endpoint_name: The name of the endpoint to generate a URL for.
        :param \**params: The path parameters to use in the URL.
        """
        self.endpoint_name = endpoint_name
        self.params = params

    def __str__(self) -> str:
        """Convert the URLFor instance to a URL string.

        :return: The generated URL as a string.
        """
        url = url_for(self.endpoint_name, **self.params)
        return str(url)

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[Any], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """Get the pydantic core schema for the URLFor type.

        This magic method allows `pydantic` to serialise URLFor
        instances, and generate a JSONSchema for them. Currently,
        URLFor instances may not be validated from strings, and
        attempting to do so will raise an error.

        The "core schema" we generate describes the field as a
        string, and serialises it by calling ``str(obj)`` which in
        turn calls our ``__str__`` method to generate the URL.

        :param source: The source type being converted.
        :param handler: The pydantic core schema handler.
        :return: The pydantic core schema for the URLFor type.
        """
        return core_schema.no_info_wrap_validator_function(
            cls._validate,
            AnyUrl.__get_pydantic_core_schema__(AnyUrl, handler),
            serialization=core_schema.to_string_ser_schema(when_used="always"),
        )

    @classmethod
    def _validate(cls, value: Any, handler: Callable[[Any], Self]) -> Self:
        """Validate and convert a value to a URLFor instance.

        :param value: The value to validate.
        :param handler: The handler to convert the value if needed.
        :return: The validated URLFor instance.
        :raises TypeError: if the value is not a URLFor instance.
        """
        if isinstance(value, cls):
            return value
        else:
            raise TypeError("URLFor instances may not be created from strings.")
