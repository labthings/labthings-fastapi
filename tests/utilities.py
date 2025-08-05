"""Useful functions for test code."""

from contextlib import contextmanager
from typing import Iterator
import pytest


@contextmanager
def raises_or_is_caused_by(
    exception_cls: type[Exception],
) -> Iterator[pytest.ExceptionInfo]:
    r"""Wrap `pytest.raises` to cope with exceptions that are wrapped in another error.

    Some errors raised during class creation are wrapped in a `RuntimeError` on older
    Python versions. This makes them harder to test for.

    This context manager checks the exception, and if it is not the expected class it
    will then check the ``__cause__`` attribute. If the ``__cause__`` matches, we
    replace the exception in the yielded ``excinfo`` object with its ``__cause__``
    so that the correct exception may be inspected.

    If neither matches, we will fail with an `AssertionError`\ .
    """
    with pytest.raises(Exception) as excinfo:
        yield excinfo
    if not isinstance(excinfo.value, exception_cls):
        assert isinstance(excinfo.value.__cause__, exception_cls)
        assert excinfo._excinfo is not None
        # If excinfo._excinfo is None, we missed an exception and the code should
        # already have failed.
        traceback = excinfo._excinfo[2]
        excinfo._excinfo = (exception_cls, excinfo.value.__cause__, traceback)
