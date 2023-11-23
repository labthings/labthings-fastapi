from __future__ import annotations
from typing import Annotated
from fastapi import Depends, Request


class FancyID:
    __globals__ = globals()  # "bake in" globals so dependency injection works

    def __init__(self, r: Request):
        self.id = 1234


FancyIDDep = Annotated[FancyID, Depends()]


class ClassDependsOnFancyID:
    __globals__ = globals()  # "bake in" globals so dependency injection works

    def __init__(self, sub: Annotated[FancyID, Depends()]):
        self.sub = sub
