# Typing tests: check `labthings_fastapi` plays nicely with `mypy`.

The codebase is type-checked with `mypy src/` and tested with `pytest`, however neither of these explicitly check that `mypy` can infer the correct types for `Thing` attributes like properties and actions. The Python files in this folder are intended to be checked using:

```terminal
mypy --warn-unused-ignores typing_tests
```

The files include valid code that's accompanied by `assert_type` statements (which check the inferred types are what we expect them to be) as well as invalid code where the expected `mypy` errors are ignored. This tests for expected errors - if an expected error is not thrown, it will cause an `unused-ignore` error.

There are more elaborate type testing solutions available, but all of them add dependencies and require us to learn a new tool. This folder of "tests" feels like a reasonable way to test that the package plays well with static type checking, without too much added complication.