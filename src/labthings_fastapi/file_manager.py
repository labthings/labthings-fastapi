"""Manage files created by Actions

Simple actions return everything you need to know about them in their return value,
which can be serialised to JSON. More complicated actions might need to return
more complicated responses, for example files.

The FileManager class is responsible for managing files created by actions. It will
handle finding a temporary storage location, and making it possible to retrieve the
files via the Invocation object.
"""
from __future__ import annotations
from uuid import UUID
from tempfile import TemporaryDirectory
from typing import Sequence, Optional
from .utilities.w3c_td_model import LinkElement
import os

class FileManager:
    """Manage files created by Actions"""
    def __init__(self, invocation_id: UUID):
        self.invocation_id = invocation_id
        self._links = {}
        self._dir = TemporaryDirectory(prefix=f"labthings-{self.invocation_id}-")

    @property
    def directory(self) -> TemporaryDirectory:
        """Return the temporary directory for this invocation"""
        return self._dir.name
    
    @property
    def filenames(self) -> list[str]:
        """A list of files currently being managed by this FileManager"""
        return os.listdir(self.directory)
    
    def add_link(self, rel: str, filename: str) -> None:
        """Make a file show up in the links of the Invocation"""
        self._links[rel] = filename

    def path(self, filename: str, rel: Optional[str]=None) -> str:
        """Return the path to a file"""
        if rel is not None:
            self.add_link(rel, filename)
        return os.path.join(self.directory, filename)
    
    def links(self, prefix: str) -> Sequence[LinkElement]:
        """Generate links to the files managed by this FileManager"""
        links = [LinkElement(rel="files", href=prefix + "/files")]
        for rel, filename in self._links.items():
            links.append(LinkElement(rel=rel, href=prefix + "/files/" + filename))
        return links