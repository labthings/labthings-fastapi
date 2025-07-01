[![codecov](https://codecov.io/gh/rwb27/labthings-fastapi/branch/main/graph/badge.svg?token=IR4QNA8X6M)](https://codecov.io/gh/rwb27/labthings-fastapi)
[![Documentation Status](https://readthedocs.org/projects/labthings-fastapi/badge/?version=latest)](https://labthings-fastapi.readthedocs.io/en/latest/?badge=latest)

# labthings-fastapi

A FastAPI based library to implement a [Web of Things] interface for laboratory hardware using Python. This is a ground-up rewrite of [python-labthings], replacing Flask 1 and Marshmallow with FastAPI and Pydantic. It is the underlying framework for v3 of the [OpenFlexure Microscope software].

Features include:

* Better alignment with the Web of Things standard:
    - `Extensions` are gone, everything is now a `Thing`
    - `Thing`s are classes, with properties and actions defined exactly once
    - Various improvements to TD generation and validation with `pydantic`
* Cleaner API
    - Datatypes of action input/outputs and properties are defined with Python type hints
    - Actions are defined exactly once, as a method of a `Thing` class
    - Properties and actions are declared using decorators (or descriptors if that's preferred)
    - Dependency injection is used to manage relationships between Things and dependency on the server
* Async HTTP handling
    - Starlette (used by FastAPI) can handle requests asynchronously - potential for websockets/events (not used much yet)
    - `Thing` code is still, for now, threaded. I intend to make it possible to write async things in the future, but don't intend it to become mandatory
* Smaller codebase
    - FastAPI more or less completely eliminates OpenAPI generation code from our codebase
    - Thing Description generation is very much simplified by the new structure (multiple Things instead of one massive Thing with many extensions)
* Extensive testing
    - FastAPI/Starlette have nice test provision, so the vast majority of the codebase is already covered


## Installation

You can install this repository with `pip install labthings-fastapi`. It may at some point be renamed to `labthings` v2. For the latest development version, either clone it and run `pip install -e .[dev]` to work on it, or just `pip install https://gitlab.com/rwb27/labthings-fastapi.git`.

## Developer notes

The code is linted with `ruff .`, type checked with `mypy src`, and tested with `pytest`. These all run in CI with GitHub Actions. The codebase is not even `v0.1` yet so it's still subject to summary rearrangement. We recommend a [pre-commit hook] to ensure `ruff` passes on every commit.

Dependencies are defined in `pyproject.toml` and can be compiled to `dev-requirements.txt` with:
```
uv pip compile --extra dev pyproject.toml --output-file dev-requirements.txt
```
If you're not using `uv`, just regular `pip-compile` from `pip-tools` should do the same thing.

All changes to the codebase should go via pull requests, and should only be merged once all the checks in the `test` job are passing. It is preferable to merge code where the `test-with-unpinned-dependencies` job fails, and deal with the dependency issues in another PR, particularly where the required changes are distinct from the code in the PR.

## Demo

See the [examples folder](./examples/) for a runnable demo.

[Web of Things]: https://www.w3.org/WoT/
[python-labthings]: https://github.com/labthings/python-labthings/
[OpenFlexure Microscope software]: https://gitlab.com/openflexure/openflexure-microscope-server/
[pre-commit hook]: https://openflexure.org/contribute#use-git-hooks-for-ci-checks
