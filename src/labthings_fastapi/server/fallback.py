import json
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.responses import RedirectResponse

app = FastAPI()

ERROR_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>LabThings</title>
</head>
<body>
    <h1>LabThings Could't Load</h1>
    <p>Something went wrong when setting up your LabThings server.</p>
    <p>Please check your configuration and try again.</p>
    <p>More details may be shown below:</p>
    <pre>{{error}}</pre>
    <p>The following Things loaded successfuly:</p>
    <ul>
        {{things}}
    </ul>
    <p>Your configuration:</p>
    <pre>{{config}}</pre>
</body>
</html>
"""

app.labthings_config = None
app.labthings_server = None
app.labthings_error = None


@app.get("/")
async def root():
    error_message = f"{app.labthings_error!r}"
    things = ""
    if app.labthings_server:
        for path, thing in app.labthings_server.things.items():
            things += f"<li>{path}: {thing!r}</li>"

    content = ERROR_PAGE
    content = content.replace("{{error}}", error_message)
    content = content.replace("{{things}}", things)
    content = content.replace("{{config}}", json.dumps(app.labthings_config, indent=2))
    return HTMLResponse(content=content, status_code=500)


@app.get("/{path:path}")
async def redirect_to_root(path: str):
    return RedirectResponse(url="/")
