"""A fallback server for LabThings.

If the ``fallback`` option is given when ``labthings-server`` is run, we will
still start an HTTP server even if we cannot run LabThings with the specified
configuration. This means that something will still be viewable at the
expected URL, which is helpful if LabThings is running as a service, or
on embedded hardware.
"""

from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
import logging
from traceback import format_exception
from typing import Any, TYPE_CHECKING

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from jinja2 import Environment, BaseLoader, select_autoescape
from starlette.responses import RedirectResponse

from .config_model import ThingServerConfig

if TYPE_CHECKING:
    from . import ThingServer

LOGGER = logging.getLogger(__name__)

_TEMPLATE_PATH = Path(__file__).with_name("fallback.html.jinja")


@dataclass(slots=True)
class FallbackContext:
    """A dataclass to provide the context of the server failing to load."""

    error: BaseException | None = None
    """The error caught when running uvicorn.run."""

    server: ThingServer | None = None
    """The ThingServer that failed to start."""

    config: ThingServerConfig | dict[str, Any] | None = None
    """The config used to set up the server.

    This can be the ThingServerConfig, or the dict read from the JSON file."""

    log_history: str | None = None
    """Any logging history to show."""


LAST_RESORT_PAGE = """
<html>
<head lang="en">
  <title>LabThings Internal Error</title>
</head>
<body>
  <h1>LabThings Internal Error</h1>
  <p>Couldn't start LabThings Server.</p>
  <p>A further error occurred when gathering context.</p>
</body>
"""


class FallbackApp(FastAPI):
    """A basic FastAPI application to serve a LabThings error page."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        r"""Set up a simple error server.

        This app is used to display a single page, which explains why the
        LabThings server cannot start.

        :param \*args: is passed to `fastapi.FastAPI.__init__`\ .
        :param \**kwargs: is passed to `fastapi.FastAPI.__init__`\ .
        """
        super().__init__(*args, **kwargs)
        try:
            # Handle dictionary config here for legacy reasons.
            self._context: FallbackContext | None = None
            self._env = Environment(
                loader=BaseLoader(),
                autoescape=select_autoescape(["html", "xml"]),
            )
            self.set_template_str(_TEMPLATE_PATH.read_text(encoding="utf-8"))
        except BaseException as e:
            # Catch any error and continue or there is no fallback server
            LOGGER.exception(e)
        self.html_code = 500

    def set_context(self, context: FallbackContext) -> None:
        """Set the fallback runtime context.

        This should be called exactly once during failure handling.

        :param context: A FallbackContext object with the server, the captured error,
            the configuration, and log history.
        """
        self._context = context

    def set_template_str(self, template_str: str) -> None:
        """Compile and set a Jinja template from a string.

        :param template_str: A Jinja2 template string. The template should be
            self-contained and must not extend or include other templates. If
            customised, the template must handle the following template context
            variables (each may be ``None``):

            - ``error_message`` (``str`` | ``None``): Error message to display, if any.
            - ``things`` (``list[str]`` | ``None``): Names of successfully loaded
                things.
            - ``config`` (``str`` | ``None``): The server configuration.
            - ``traceback`` (``str`` | ``None``): Formatted error traceback.
            - ``logginginfo`` (``str`` | ``None``): Captured logging output.
        """
        self._template = self._env.from_string(template_str)

    def fallback_page(self) -> HTMLResponse:
        """Generate the fallback page and return it as an HTMLResponse.

        :return: The HTMLResponse for the fallback page.
        :raises RuntimeError: if the fallback context was never set.
        """
        try:
            if self._context is None:
                raise RuntimeError("Not context set for fallback server.")
            error_message, error_w_trace = _format_error_and_traceback(self._context)
            things = list(self._context.server.things) if self._context.server else []

            if isinstance(self._context.config, ThingServerConfig):
                conf_str = self._context.config.model_dump_json(indent=2)
            else:
                conf_str = json.dumps(self._context.config, indent=2)

            content = app._template.render(
                error_message=error_message,
                things=things,
                config=conf_str,
                traceback=error_w_trace,
                logginginfo=self._context.log_history,
            )

            return HTMLResponse(content=content, status_code=app.html_code)
        except BaseException as e:
            # Catch any error and continue or there is no fallback server
            LOGGER.exception(e)
            return HTMLResponse(content=LAST_RESORT_PAGE, status_code=500)


app = FallbackApp()


@app.get("/")
async def root() -> HTMLResponse:
    """Display the LabThings error page.

    :return: a response that serves the error as an HTML page.
    """
    return app.fallback_page()


def _format_error_and_traceback(context: FallbackContext) -> tuple[str, str]:
    """Format the error and traceback.

    If the error was in lifespan causing Uvicorn to raise SystemExit(3) without a
    traceback. Try to extract the saved exception from the server.

    :param context:The FallbackContext object with all fallback information.

    :return: A tuple of error message and error traceback.
    """
    err = context.error
    server = context.server
    error_message = f"{err}"

    if (
        isinstance(err, SystemExit)
        and server is not None
        and isinstance(server.startup_failure, dict)
    ):
        # It is a uvicorn SystemExit, so replace err with the saved error in the server.
        err = server.startup_failure.get("exception", err)
        thing = server.startup_failure.get("thing", "Unknown")
        error_message = f"Failed to enter '{thing}' Thing: {err}"

    # use traceback.format_exception to get full traceback as list
    # this ends in newlines, but needs joining to be a single string
    error_w_trace = "".join(format_exception(err))
    return error_message, error_w_trace


@app.get("/{path:path}")
async def redirect_to_root(path: str) -> RedirectResponse:
    """Redirect all paths on the server to the error page.

    If any URL other than the error page is requested, this server will
    redirect it to the error page.

    :param path: The path requested.

    :return: a response redirecting to the error page.
    """
    return RedirectResponse(url="/")
