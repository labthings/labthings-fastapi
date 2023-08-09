[![codecov](https://codecov.io/gh/rwb27/labthings-fastapi/branch/main/graph/badge.svg?token=IR4QNA8X6M)](https://codecov.io/gh/rwb27/labthings-fastapi)

# labthings-fastapi
An experimental implementation of a LabThings server using fastapi.

This is currently an incomplete implementation of the WoT specification, and will gradually grow as required to support the OpenFlexure server.

## Installation

You can install this repository with `pip`, either clone it and run `pip install -e .[dev]` to work on it, or just `pip install https://gitlab.com/rwb27/labthings-fastapi.git`.

## Developer notes

The code is linted with `ruff .`, type checked with `mypy src`, and tested with `pytest`. These all run in CI with GitHub Actions. The codebase is not even `v0.0.1` yet so it's still subject to summary rearrangement.

## Demo

See the [examples folder](./examples/) for a runnable demo.
