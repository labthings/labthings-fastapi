# Testing `labthings-fastapi`

Our test suite ensures the framework functions correctly, maintains code quality, and integrates seamlessly with static type checkers.

## Continuous Integration (CI) Pipeline

When you submit a Pull Request (PR), our GitHub Actions CI pipeline automatically runs a comprehensive suite of checks. Your PR must pass these checks before it can be merged.

Here is what the CI pipeline tests:

* **Matrix Testing:** We run the core test suite (`pytest`) and static type checks (`mypy`) across Python versions 3.10, 3.11, 3.12, and 3.13.
* **Code Quality & Security:** The pipeline runs `ruff` (formatting and linting), `flake8` (docstrings), `codespell` (spelling), and a `pip-audit` to check for dependency vulnerabilities.
* **Coverage:** We track code coverage. A report is generated on your PR to show if your changes increased or decreased overall test coverage.
* **Dependency Checks:** We run the tests twice: once with pinned dependencies (`dev-requirements.txt`) for reproducibility, and once with unpinned dependencies (`.[dev]`) to catch upstream breakages early.
* **Downstream Integration:** The pipeline installs your version of `labthings-fastapi` alongside the `v3` branch of the OpenFlexure Microscope Server. It then runs the entire OFM test suite (unit, integration, and lifecycle) to guarantee backwards compatibility. *(Note: You can target a specific OFM branch by adding `OFM-Feature-Branch: branch-name` to your PR description).*

---

## Running Core Tests Locally

To ensure your code will pass CI, you should run these checks locally before pushing your commits.

### 1. Local Environment Setup

We recommend running the test suite using the pinned development dependencies to mirror the primary CI environment. Ensure you have cloned the repository, then install the package and dependencies:

```bash
git clone https://github.com/labthings/labthings-fastapi.git
cd labthings-fastapi
pip install -e . -r dev-requirements.txt
```

### 2. Linting, Formatting, and Spelling

Check that your code adheres to the project's formatting and style guidelines from the root of the repository:

* **Linting:** `ruff check .`
* **Formatting:** `ruff format --check .`
* **Spelling:** `codespell .`
* **Docstrings:** `flake8 src`

### 3. Static Type Checking

`labthings-fastapi` is designed to be fully type-hinted. We explicitly test that `mypy` can infer the correct types for `Thing` attributes. Run static type checking across the source code and our dedicated typing tests folder:

```bash
mypy
```

### 4. Unit Tests & Coverage

We use `pytest` for our core test suite. Execute the unit tests and generate a coverage report using:

```bash
pytest
```

---

## Downstream Integration Testing Locally

Because `labthings-fastapi` underpins the [OpenFlexure Microscope software], major architectural changes should be tested against the downstream server locally. This matches the `test-against-ofm-v3` job in our CI pipeline.

Assuming you have both repositories cloned in the same parent directory:

```bash
# 1. Setup the OpenFlexure Microscope Server
cd ../openflexure-microscope-server
git checkout v3
pip install -e .[dev]

# 2. Install your local version of labthings-fastapi
pip install -e ../labthings-fastapi

# 3. Pull the OFM web app (required for integration)
python ./pull_webapp.py

# 4. Run the OFM Test Suite
pytest                                     # Run OFM unit tests
pytest tests/integration_tests             # Run OFM integration tests
python tests/lifecycle_test/testfile.py    # Run OFM lifecycle tests
mypy src                                   # Run OFM static type checks
```

[OpenFlexure Microscope software]: https://gitlab.com/openflexure/openflexure-microscope-server/