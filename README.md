[![codecov](https://codecov.io/gh/rwb27/labthings-fastapi/branch/main/graph/badge.svg?token=IR4QNA8X6M)](https://codecov.io/gh/rwb27/labthings-fastapi)
[![Documentation Status](https://readthedocs.org/projects/labthings-fastapi/badge/?version=latest)](https://labthings-fastapi.readthedocs.io/en/latest/?badge=latest)

# labthings-fastapi

A FastAPI based library to implement a [Web of Things] interface for laboratory hardware using Python. This is a ground-up rewrite of [python-labthings], based on FastAPI and Pydantic. It is the underlying framework for v3 of the [OpenFlexure Microscope software].

Documentation, including install instructions, is available on [readthedocs].

## Installation

See [readthedocs] for installation instructions that are automatically tested. You can install this package with `pip install labthings-fastapi`.


### Installation Notes

`labthings-fastapi` supports **Python 3.10, 3.11, 3.12, and 3.13**. The upper limit is strictly capped at 3.13 due to current `pydantic-core` dependencies.

> **Note: Windows Installations on devices with ARM processors**
>
> Installing on Windows devices with ARM processors requires Visual Studio with the **"Desktop development with C++"** workload enabled. This is necessary because `pydantic` relies on Rust, which in turn requires C++ build tools to compile.
>
> *If you are using a centrally managed machine, you will need administrator privileges to install these system-level dependencies.*

For instructions on how to set up a development environment, run tests, and contribute to this project, please see [CONTRIBUTING.md].

## Demo

See [readthedocs] for a runnable demo.

[Web of Things]: https://www.w3.org/WoT/
[python-labthings]: https://github.com/labthings/python-labthings/
[OpenFlexure Microscope software]: https://gitlab.com/openflexure/openflexure-microscope-server/
[pre-commit hook]: https://openflexure.org/contribute#use-git-hooks-for-ci-checks
[readthedocs]: https://labthings-fastapi.readthedocs.io/
[CONTRIBUTING.md]: ./CONTRIBUTING.md
