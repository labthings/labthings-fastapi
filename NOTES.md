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
* `descriptors` will need to properly describe the lifecycle of `thing_setting` and/or eliminate it in favour of always using the descriptor.
* More detail of how and why to use dependencies other than the inter-thing dependencies.
* A description of how actions are cancelled, perhaps in the new actions page?
* A description of how the various dependencies work together to set up a new action - e.g. `InvocationID`, `CancelHook`, ... - added to module docstring
* A description of notifications/observers, including current status and planned improvements.
* Mention `fastapi_endpoint` somewhere that talks about defining `Thing`s
* Server configuration files.
* A page on documentation (Thing Description vs OpenAPI), I find there are many references to "TD and OpenAPI" anbd it would be nice to have a single target.

## Code to tidy up or check
* `actions/__init__.py:377` I've removed `as_responses` as it should always be true - this makes type hints correct. I should make `request` non-optional and update the 2 places where it's called.
* `actions/__init__.py:191` I tried typing this as `ActionDescriptor` but this cases confusion because `mypy` seems to think the descriptor returned by the property will then be invoked with `__get__`. This is not correct. For now, I have removed the type annotation again to avoid the confusion. The resolution might be as simple as turning the `action` property into a method, but we should consider this more carefully with some testing rather than have me bodge it now.
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
* `blocking_portal` should probably just be a property of `.Thing`.
* `dependencies/blocking_portal.py:49` I don't expect this exception to be raised. Is it worth a custom error? Or a test?
* I've added `direct_thing_client_class` to `deps` and updated the dependencies example to use it. This is a change to recommended usage but not a change to the API beyond exposing another symbol.
* `descriptors/action.py:198` has an Exception-swallowing block. If this is needed, we should make it more specific or justify why not.
* `descriptors/property.py` will be substantially rewritten. I have copied over docstrings from another branch that describe the status quo, I realise they are confusing, but that's why we plan to change the module significantly.
* `example_things/__init__.py` should be split up and renamed. Most of the things belong in tests, not in the module.
* `outputs/blob/blob.py` should use custom exceptions for `retrieve_data` and `to_dict`. We also need more unit tests for blobs, including error conditions and invalid URLs.
  - 428: should use a custom exception, possibly based on `AttributeError`.
  - 535: should use generic class methods to ensure the return type is an instance of `cls` rather than `Blob`. Same for `from_bytes`.
* `docs/src/blobs.rst` could really do with doctest to stop the example going stale
* `outputs/mjpeg_stream.py` could be simplified.
  - `buffer_for_reading` is a pointless context manager, could be replaced with `ringbuffer_entry`
  - many generic `RuntimeErrors` should have exceptions defined.
  - Should we use `IndexError` when frames aren't available (or at least a subclass thereof)?
  - Example code in the descriptor may want a doctest in due course.
  - Could do with example code showing how it works in a simple camera?
* `server`: could do with some more specific exceptions.
* `server.cli`: need a model for config.
* `thing_description`:
  - Custom exception for `recursion_limit`
* `utilities`:
  - `LabThingsObjectData` probably doesn't need to be a pydantic dataclass.
    - Do we want to centralise other key data in here, like `_settings_file_path` and `_labthings_blocking_portal`?
  - `introspection`:
    - There's a confusing TODO about path parameters in `fastapi_dependency_params`
    - There's a ValueError that might want subclassing in `input_model_from_signature`.
  - `exceptions` will need to hoover up more exceptions. Do we define them here? probably yes...
* `notifications` is empty - need to consolidate code from property/action/websocket.
* `thing`:
  - consolidate settings into an object?
  - default `thing_state` does cacheing but this isn't really documented. Remove?
  - thing_description should consolidate `path` and `base_url`. In fact, if we set `base_url` to be the path
    to the TD, we can make everything else static.
* General: there are a lot of class attributes/annotations that should maybe be in `__init__`. We need to pick a convention and stick to it, I have often defined class attrs next to the function(s) that use them, but that might be bad style?



