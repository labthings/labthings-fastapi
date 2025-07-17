"""A fallback server for LabThings.

If the ``fallback`` option is given when ``labthings-server`` is run, we will
still start an HTTP server even if we cannot run LabThings with the specified
configuration. This means that something will still be viewable at the
expected URL, which is helpful if LabThings is running as a service, or
on embedded hardware.
"""

import json
from traceback import format_exception
from typing import Any
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.responses import RedirectResponse


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
        self.labthings_config = None
        self.labthings_server = None
        self.labthings_error = None
        self.log_history = None
        self.html_code = 500


app = FallbackApp()

ERROR_PAGE = """
<!DOCTYPE html>
<html>
<head lang="en">
    <title>LabThings</title>
    <style>
    pre {
        white-space: pre-wrap;
        overflow-wrap: anywhere;
    }
    </style>
</head>
<body>
    <h1>LabThings Could't Load</h1>
    <p>Something went wrong when setting up your LabThings server.</p>
    <p>Please check your configuration and try again.</p>
    <p>More details may be shown below:</p>
    <pre>{{error}}</pre>
    <p>The following Things loaded successfully:</p>
    <ul>
        {{things}}
    </ul>
    <p>Your configuration:</p>
    <pre>{{config}}</pre>
    <p>Traceback</p>
    <pre>{{traceback}}</pre>
    {{logginginfo}}
</body>
</html>
"""


@app.get("/")
async def root() -> HTMLResponse:
    """Display the LabThings error page.

    :return: a response that serves the error as an HTML page.
    """
    error_message = f"{app.labthings_error}"
    # use traceback.format_exception to get full traceback as list
    # this ends in newlines, but needs joining to be a single string
    error_w_trace = "".join(format_exception(app.labthings_error))
    things = ""
    if app.labthings_server:
        for path, thing in app.labthings_server.things.items():
            things += f"<li>{path}: {thing!r}</li>"

    content = ERROR_PAGE
    content = content.replace("{{error}}", error_message)
    content = content.replace("{{things}}", things)
    content = content.replace("{{config}}", json.dumps(app.labthings_config, indent=2))
    content = content.replace("{{traceback}}", error_w_trace)

    if app.log_history is None:
        logging_info = "    <p>No logging info available</p>"
    else:
        logging_info = f"    <p>Logging info</p>\n    <pre>{app.log_history}</pre>"

    content = content.replace("{{logginginfo}}", logging_info)
    return HTMLResponse(content=content, status_code=app.html_code)


@app.get("/{path:path}")
async def redirect_to_root(path: str) -> RedirectResponse:
    """Redirect all paths on the server to the error page.

    If any URL other than the error page is requested, this server will
    redirect it to the error page.

    :param path: The path requested.

    :return: a response redirecting to the error page.
    """
    return RedirectResponse(url="/")
