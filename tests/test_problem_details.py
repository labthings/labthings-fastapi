"""Test we can generate problem details to describe exceptions nicely."""

import pytest

from labthings_fastapi import problem_details, exceptions

DOCS_URL = (
    "https://labthings-fastapi.readthedocs.io/en/latest/"
    "autoapi/labthings_fastapi/exceptions/index.html"
)


class CustomError(Exception):
    """A custom exception."""


ERROR_URLS = [
    # Some standard-library exceptions
    (BaseException, "https://docs.python.org/3/library/exceptions.html#BaseException"),
    (Exception, "https://docs.python.org/3/library/exceptions.html#Exception"),
    (RuntimeError, "https://docs.python.org/3/library/exceptions.html#RuntimeError"),
    # Some LabThings exceptions
    (
        exceptions.FeatureNotAvailableError,
        f"{DOCS_URL}#labthings_fastapi.exceptions.FeatureNotAvailableError",
    ),
    (
        exceptions.InvocationCancelledError,
        f"{DOCS_URL}#labthings_fastapi.exceptions.InvocationCancelledError",
    ),
    # Custom exceptions should be None
    (CustomError, None),
]


@pytest.mark.parametrize(("err", "url"), ERROR_URLS)
def test_docs_url(err, url):
    """Check URLs for built-in and LabThings errors, and that we get None for others."""
    assert problem_details.docs_url(err) == url


@pytest.mark.parametrize(("err", "url"), ERROR_URLS)
def test_pd_from_exception(err, url):
    pd = problem_details.ProblemDetails.from_exception(err("Message"))
    assert pd.type == url
    assert pd.detail == "Message"
    assert pd.title == err.__name__
    try:
        assert pd.status == err.status_code
    except AttributeError:
        assert pd.status == 500
