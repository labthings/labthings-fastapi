# labthings-fastapi
An experimental implementation of a LabThings server using fastapi.

This is currently an incomplete implementation of the WoT specification, and will gradually grow as required to support the OpenFlexure server.

## installation

This is for my reference, until it's properly packaged:

```
git clone git@github.com:rwb27/labthings-fastapi.git
cd labthings-fastapi
python --version
python -m venv .venv --prompt="LabThings-FastAPI"
source .venv/bin/activate # Windows: .venv/Scripts/activate
pip install -e .
```

## Demo

See the [examples folder](./examples/) for a runnable demo.
