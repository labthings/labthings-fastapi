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
* In general, it would probably help developers to detail the code flow for the main activities. That's probably in its own developer-focused section of the docs, but I could see it really helping to describe, in some detail,
    - How an Action is run, including the POST and subsequent GET requests, the resolving of dependencies, where the endpoint is defined, how the thread is started and monitored, and which functions are threaded vs async.
    - How a Thing is defined, how its endpoints are generated, and how the Thing Description is made
    - How properties work: get and set from Python vs HTTP
    - MJPEG Stream: what code is threaded, what is async, and how we communicate between the two.

## Code to tidy up or check
* `actions/__init__.py:377` I've removed `as_responses` as it should always be true - this makes type hints correct. I should make `request` non-optional and update the 2 places where it's called.
* `descriptors/action.py:254` should probably have a `Response` dependency and pass it to `list_invocations`.
* `actions/invocation_model.py:47` might be better typed as `LogRecord`?
* `client`
    * [x] General: rename `task` to `invocation` to match naming conventions elsewhere. This is done in `__init__` and tests pass.
    * General: replace `ClientBlobOutput` with `Blob` and get rid of `ClientBlobOutput`.
    * `client/__init__.py:234`: should this have `BaseModel` or `type[BaseModel]`? We're looking for the (sub)class, not an instance...
    * `client/__init__.py:24`: `_get_link` needs error checking and might want to make use of the Model for links.
    * `client/in_server.py` needs a fairly thorough rewrite. It is probably efficient to do this after client code generation is merged.
* `outputs/mjpeg_stream.py`: review the locks and stream termination
* `tests/` still uses `poll_task` from `temp_client.py`. We should use `poll_invocation` from `client` instead (it's identical). We should also review how `TestClient` is used and perhaps make more use of the client module. This might want to wait until after code generation is implemented, as that will substantially change the client module.