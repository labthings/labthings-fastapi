[![codecov](https://codecov.io/gh/rwb27/labthings-fastapi/branch/main/graph/badge.svg?token=IR4QNA8X6M)](https://codecov.io/gh/rwb27/labthings-fastapi)
[![Documentation Status](https://readthedocs.org/projects/labthings-fastapi/badge/?version=latest)](https://labthings-fastapi.readthedocs.io/en/latest/?badge=latest)

# labthings-fastapi

A FastAPI based library to implement a [Web of Things] interface for laboratory hardware using Python. This is a ground-up rewrite of [python-labthings], based on FastAPI and Pydantic. It is the underlying framework for v3 of the [OpenFlexure Microscope software].

Documentation, including install instructions, is available on [readthedocs].

## Installation

See [readthedocs] for installation instructions that are automatically tested. You can install this package with `pip install labthings-fastapi`.

## Developer notes

For the latest development version, clone this repository and run `pip install -e .[dev]`. 

The code is linted with `ruff .`, type checked with `mypy`, and tested with `pytest`. These all run in CI with GitHub Actions. We recommend a [pre-commit hook] to ensure `ruff` passes on every commit. `flake8` is also run in CI, primarily to enable stricter checks on docstrings. It is run as `flake8 src`. `ruff` and `flake8` are both configured from `pyproject.toml`.

All changes to the codebase should go via pull requests, and should only be merged once all the checks in the `test` job are passing. It is preferable to merge code where the `test-with-unpinned-dependencies` job fails, and deal with the dependency issues in another PR, particularly where the required changes are distinct from the code in the PR.

Dependencies are defined in `pyproject.toml` and can be compiled to `dev-requirements.txt` with:
```
uv pip compile --extra dev pyproject.toml --output-file dev-requirements.txt
```
If you're not using `uv`, just regular `pip-compile` from `pip-tools` should do the same thing.

## Demo

See [readthedocs] for a runnable demo.

[Web of Things]: https://www.w3.org/WoT/
[python-labthings]: https://github.com/labthings/python-labthings/
[OpenFlexure Microscope software]: https://gitlab.com/openflexure/openflexure-microscope-server/
[pre-commit hook]: https://openflexure.org/contribute#use-git-hooks-for-ci-checks
[readthedocs]: https://labthings-fastapi.readthedocs.io/
