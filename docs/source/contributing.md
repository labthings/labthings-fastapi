# Contributing to labthings-fastapi

First off, thank you for considering contributing to `labthings-fastapi`! We welcome contributions from everyone, whether it's reporting a bug, suggesting a feature, improving documentation, or writing code.

This document outlines the processes for getting help, reporting issues, and contributing to the codebase.

## Seeking Support

If you have a question about how to use `labthings-fastapi`, or if you are running into trouble:

* **Check the Documentation:** Please review the official documentation on [readthedocs].
* **GitHub Discussions / Issues:** If you cannot find the answer, feel free to open an issue on our [GitHub Issues page].
* **OpenFlexure Community:** Because `labthings-fastapi` is the underlying framework for v3 of the [OpenFlexure Microscope software], you may also find support by engaging with the broader [OpenFlexure Forum].

## Reporting Issues or Bugs

If you find a bug or have a feature request, please report it by opening an issue on our [GitHub Issues page].

When reporting an issue, please include as much detail as possible:

* **Description:** A clear and concise description of what the bug is.
* **Reproduction steps:** How can we reproduce the problem? (A minimal reproducible example is highly appreciated).
* **Expected behaviour:** What did you expect to happen?
* **Environment:** Include your OS, Python version, and `labthings-fastapi` version. Include full error tracebacks if applicable.

## Contributing Code or Documentation

We welcome pull requests for bug fixes, new features, and documentation improvements.

### 1. Local Development Setup

To work on the code, you will need to clone the repository and install the development dependencies.
Please see the [installation notes](./README.md#installation-notes) for more detail about compatible Python versions and Windows installation.

```bash
# Clone the repository
git clone https://github.com/labthings/labthings-fastapi.git
cd labthings-fastapi

# Install the package in editable mode with development dependencies
pip install -r dev-requirements.txt
```

### 2. Linting and Testing

We use several tools to maintain code quality. All of these run in CI with [GitHub Actions], but you should run them locally before submitting a Pull Request. Both `ruff` and `flake8` are configured from [`pyproject.toml`].

More detailed information on our testing and linting can be found in our [Testing Guidelines].

* **Linting:** We use [`ruff`] for fast linting and formatting. We highly recommend setting up a pre-commit hook to ensure [`ruff`] passes on every commit.
  ```bash
  ruff format --check
  ruff check .
  ```

* **Docstrings:** [`flake8`] is primarily used to enable stricter checks on docstrings.
  ```bash
  flake8 src
  ```

* **Spelling:** We use [`codespell`] to prevent common spelling mistakes in code and documentation.
  ```bash
  codespell .
  ```

* **Type Checking:** We use [`mypy`] for static type checking. It is configured in `pyproject.toml`.
  ```bash
  mypy
  ```

* **Testing:** We use [`pytest`] for our test suite and test coverage. Ensure all tests pass locally.
  ```bash
  pytest --cov=src
  ```

### 3. Managing Dependencies

Dependencies are defined in [`pyproject.toml`]. If you need to compile a `dev-requirements.txt` file (e.g., for reproducible CI/CD or local isolated environments), you can do so using [`uv`]:

```bash
uv pip compile --extra dev pyproject.toml --output-file dev-requirements.txt
```

*(If you're not using `uv`, regular `pip-compile` from `pip-tools` will achieve the same thing).*

### 4. Submitting a Pull Request (PR)

All changes to the codebase must go via pull requests. Unless you are a core maintainer with write access, please use the standard fork-and-branch workflow:

1. **Fork the repository** to your own GitHub account using the "Fork" button at the top of the repository page.
2. **Clone your fork** locally and set up the upstream remote:
   ```bash
   git clone https://github.com/YOUR-USERNAME/labthings-fastapi.git
   cd labthings-fastapi
   git remote add upstream https://github.com/labthings/labthings-fastapi.git
   ```
3. **Create a new branch** for your feature or bugfix:
   ```bash
   git checkout -b feature-name
   ```
4. **Commit your changes** with clear, descriptive commit messages.
5. **Push your branch** up to your fork:
   ```bash
   git push origin feature-name
   ```
6. **Open a Pull Request** against the `main` branch of the `labthings/labthings-fastapi` repository.

**Pull Request Guidelines:**

* Code should only be merged once all the checks in the CI test job are passing.
* **Unpinned Dependencies:** Note that we have a specific CI job called `test-with-unpinned-dependencies`. It is acceptable to merge code if only this specific job fails, provided the failure is due to upstream dependency issues. We prefer to deal with upstream dependency issues in a separate PR, particularly when the required fixes are distinct from the code in your current PR. The same applies to the `pip-audit` job.
* Update documentation (`docs/` or docstrings) if your changes modify existing behavior or add new features.

[readthedocs]: https://labthings-fastapi.readthedocs.io/
[GitHub Issues page]: https://github.com/labthings/labthings-fastapi/issues
[OpenFlexure Forum]: https://openflexure.discourse.group/
[OpenFlexure Microscope software]: https://gitlab.com/openflexure/openflexure-microscope-server/
[GitHub Actions]: https://github.com/labthings/labthings-fastapi/actions
[`ruff`]: https://docs.astral.sh/ruff/
[`pyproject.toml`]: ./pyproject.toml
[`flake8`]: https://flake8.pycqa.org/en/latest/
[`mypy`]: https://mypy-lang.org/
[`pytest`]: https://docs.pytest.org/en/stable/
[`uv`]: https://docs.astral.sh/uv/
[Testing Guidelines]: ./testing.md