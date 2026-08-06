"""Test we can generate problem details to describe exceptions nicely."""

import httpx2
import pytest
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from labthings_fastapi import exceptions, problem_details

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


# There are some valid ProblemDetails instances that couldn't be made by
# from_exception (for example, if detail or status is missing). We
# extend the list of test cases to include these.
PD_INSTANCES = [
    *[
        problem_details.ProblemDetails.from_exception(exc("Message"))
        for exc, _url, _code in ERRORS
    ],
    problem_details.ProblemDetails(detail="Message"),
    problem_details.ProblemDetails(detail="Message", status=501),
    problem_details.ProblemDetails(),
    problem_details.ProblemDetails(instance="Instance-specific message."),
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


def evaluate_response(response: Response) -> httpx2.Response:
    """Use a TestClient to turn a Starlette Response into an httpx2 one.

    This allows us to easily evaluate the body of a Response object.
    This will create an ephemeral `TestClient` object. Doing so is not
    massively efficient, but it doesn't slow down tests unduly and it
    minimises custom code.

    :param response: a `fastapi.Response` object.
    :return a `httpx2.Response` object.
    """
    app = FastAPI()

    @app.get("/")
    def return_error() -> Response:
        return response

    with TestClient(app) as tc:
        return tc.get("/")


@pytest.mark.parametrize("pd", PD_INSTANCES)
def test_response_from_exception(pd):
    response = evaluate_response(pd.json_response())

    assert response.status_code == pd.status or 500
    value = response.json()
    assert value == pd.model_dump()


def test_exceptions_to_problem_details_noerror(mocker):
    """Check the `exceptions_to_problem_details` decorator with no error."""

    response = JSONResponse("success!", status_code=200)
    logger = mocker.Mock()

    @problem_details.exceptions_to_problem_details(logger=logger)
    def successful():
        return response

    # The function should complete with no error and return the value
    assert successful() is response

    # Our mocked logger should record nothing
    assert logger.error.called is False


@pytest.mark.parametrize(("err", "url", "code"), ERRORS)
def test_exceptions_to_problem_details_error(err, url, code, mocker):
    """Check exceptions produce a response with the right message."""
    logger = mocker.Mock()

    @problem_details.exceptions_to_problem_details(logger=logger)
    def fails():
        raise err("Message")

    if not issubclass(err, Exception):
        # BaseException (and other non-Exception errors) isn't caught.
        with pytest.raises(err):
            fails()
        return

    # The function should complete, but the returned response describes
    # the error.
    response = evaluate_response(fails())
    assert response.status_code == code
    value = response.json()
    assert value["type"] == url
    assert value["detail"] == "Message"
    assert value["title"] == err.__name__
    assert value["status"] == code

    # Our mocked logger should record an error
    assert logger.error.call_count == 1
    assert isinstance(logger.error.call_args[0][0], err)
    assert str(logger.error.call_args[0][0]) == "Message"
