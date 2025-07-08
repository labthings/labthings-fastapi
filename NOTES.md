# Docstring Review

In this PR, I intend to go through every function and check:
* That there is a docstring
* That it's formatted appropriately, using ReST

I will add missing docstrings as I go. I will note here any conceptual docs that are missing - probably looking through all the code is a good way to identify these. I may not add them in this PR, but will at least make an issue to flag them.

This file will be deleted before merging.

## Linting

The `pydoclint` rules in `ruff` unfortunately don't seem to be configurable for Sphinx-style docstrings. I have now
switched to using `pydoclint` directly, and configured it in `pyproject.toml`. It seems to be quite fast.

## Conceptual pages needed

* `actions.__init__` may want some content moving between module level docstring and a conceptual page. Actions are described in a couple of places but we need an overview of how the mechanism works.

## Code to tidy up or check
* `actions/__init__.py:377` I've removed `as_responses` as it should always be true - this makes type hints correct. I should make `request` non-optional and update the 2 places where it's called.
* `descriptors/action.py:254` should probably have a `Response` dependency and pass it to `list_invocations`.
* `actions/invocation_model.py:47` might be better typed as `LogRecord`?