"""Manage files created by Actions

Simple actions return everything you need to know about them in their return value,
which can be serialised to JSON. More complicated actions might need to return
more complicated responses, for example files.

The FileManager class is responsible for managing files created by actions. It will
handle finding a temporary storage location, and making it possible to retrieve the
files via the Invocation object.
"""

from __future__ import annotations
from tempfile import TemporaryDirectory
from typing import Annotated, Sequence, Optional

from fastapi import Depends, Request

from .thing_description.model import LinkElement
import os

from .dependencies.invocation import InvocationID


class FileManager:
    """Manage files created by Actions"""

    __globals__ = globals()  # "bake in" globals so dependency injection works

    def __init__(self, invocation_id: InvocationID, request: Request):
        self.invocation_id = invocation_id
        self._links: set[tuple[str, str]] = set()
        self._dir = TemporaryDirectory(prefix=f"labthings-{self.invocation_id}-")
        request.state.file_manager = self
        # The request state will be used to hold onto the FileManager after
        # the action has finished

    @property
    def directory(self) -> str:
        """Return the temporary directory for this invocation"""
        return self._dir.name

    @property
    def filenames(self) -> list[str]:
        """A list of files currently being managed by this FileManager"""
        return os.listdir(self.directory)

    def add_link(self, rel: str, filename: str) -> None:
        """Make a file show up in the links of the Invocation"""
        self._links.add((rel, filename))

    def path(self, filename: str, rel: Optional[str] = None) -> str:
        """Return the path to a file"""
        if rel is not None:
            self.add_link(rel, filename)
        return os.path.join(self.directory, filename)

    def links(self, prefix: str) -> Sequence[LinkElement]:
        """Generate links to the files managed by this FileManager"""
        links = [LinkElement(rel="files", href=prefix + "/files")]
        for rel, filename in self._links:
            links.append(LinkElement(rel=rel, href=prefix + "/files/" + filename))
        return links


FileManagerDep = Annotated[FileManager, Depends()]
