"""A module for testing dependencies.

This module provides some classes that are used as dependencies by unit tests.
Note that `from __future__ import annotations` is not used here. If it is used,
we would need to add the following to the classes:

.. code-block:: python

    class Whatever:
        __globals__ = globals()  # "bake in" globals so dependency injection works

This relates to the way FastAPI resolves annotations to objects. There's an issue
thread that discusses the work-around above explicitly, but it's part of a bigger
issue discussed here:

https://github.com/pydantic/pydantic/issues/2678

"""

from dataclasses import dataclass
from typing import Annotated
from fastapi import Depends, Request


class FancyID:
    def __init__(self, r: Request):
        self.id = 1234


FancyIDDep = Annotated[FancyID, Depends()]


@dataclass
class ClassDependsOnFancyID:
    """A dataclass that will request a FancyID when used as a Dependency."""

    sub: FancyIDDep
