"""Test we can generate problem details to describe exceptions nicely."""

import pytest

from labthings_fastapi import problem_details, exceptions

DOCS_URL = (
    "https://labthings-fastapi.readthedocs.io/en/latest/"
    "autoapi/labthings_fastapi/exceptions/index.html"
    "#labthings_fastapi.exceptions."
)
PYTHON_DOCS = "https://docs.python.org/3/library/exceptions.html"


class CustomError(Exception):
    """A custom exception."""


ERRORS = [
    # Some standard-library exceptions
    (BaseException, f"{PYTHON_DOCS}#BaseException", 500),
    (Exception, f"{PYTHON_DOCS}#Exception", 500),
    (RuntimeError, f"{PYTHON_DOCS}#RuntimeError", 500),
    # Some LabThings exceptions
    (exceptions.FeatureNotAvailableError, f"{DOCS_URL}FeatureNotAvailableError", 500),
    (exceptions.InvocationCancelledError, f"{DOCS_URL}InvocationCancelledError", 500),
    (exceptions.GlobalLockBusyError, f"{DOCS_URL}GlobalLockBusyError", 409),
    # Custom exceptions should be None
    (CustomError, None, 500),
]


@pytest.mark.parametrize(("err", "url", "_code"), ERRORS)
def test_docs_url(err, url, _code):
    """Check URLs for built-in and LabThings errors, and that we get None for others."""
    assert problem_details.docs_url(err) == url


@pytest.mark.parametrize(("err", "url", "code"), ERRORS)
def test_pd_from_exception(err, url, code):
    pd = problem_details.ProblemDetails.from_exception(err("Message"))
    assert pd.type == url
    assert pd.detail == "Message"
    assert pd.title == err.__name__
    assert pd.status == code
