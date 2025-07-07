import json
from traceback import format_exception
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.responses import RedirectResponse


class FallbackApp(FastAPI):
    def __init__(self, *args, **kwargs):
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
async def root():
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
async def redirect_to_root(path: str):
    return RedirectResponse(url="/")
