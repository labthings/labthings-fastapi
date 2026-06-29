"""JSON representations of errors as per RFC 9457.

This module defines a model and supporting functions that help to create
"Problem Details" objects to represent errors in HTTP responses.
"""

from typing_extensions import Self

from pydantic import BaseModel, ConfigDict
from labthings_fastapi import exceptions


class ProblemDetails(BaseModel):
    """A model to describe an error that occurred in an invocation."""

    model_config = ConfigDict(extra="allow")

    detail: str | None = None
    """A human-readable string with details of the error."""
    type: str | None = None
    """A URI giving a unique reference for the error."""
    status: int | None = None
    """An HTTP status code describing the error."""
    title: str | None = None
    """A human-readable title for the error."""
    instance: str | None = None
    """A URI that may or may not give details about this specific instance."""

    @classmethod
    def from_exception(cls, exc: BaseException) -> Self:
        r"""Generate a `ProblemDetails` model from an exception instance.

        :param exc: the exception instance to be described.
        :return: a `ProblemDetails` object describing ``exc``\ .
        """
        return cls(
            detail=str(exc),
            type=docs_url(type(exc)),
            title=exc.__class__.__name__,
            status=getattr(exc, "status_code", 500),
        )


# This URL should describe all exceptions in this module.
DOCS_URL = (
    "https://labthings-fastapi.readthedocs.io/en/latest/"
    "autoapi/labthings_fastapi/exceptions/index.html"
)
PYTHON_DOCS_URL = "https://docs.python.org/3/library/exceptions.html"


def docs_url(exc: type[BaseException]) -> str | None:
    """Return a URL identifying a LabThings exception.

    :param exc: An exception class.
    :return: a URL pointing to that exception in the docs, or
        `None` if the exception is not in this module.
    """
    if exc.__module__ == exceptions.__name__:
        return f"{DOCS_URL}#{exc.__module__}.{exc.__qualname__}"
    if exc.__module__ == "builtins":
        return f"{PYTHON_DOCS_URL}#{exc.__name__}"
    return None
