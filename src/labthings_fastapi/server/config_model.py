r"""Pydantic models to enable server configuration to be loaded from file.

The models in this module allow `.ThingConfig` dataclasses to be constructed
from dictionaries or JSON files. They also describe the full server configurtion
with `.ServerConfigModel`\ . These models are used by the `.cli` module to
start servers based on configuration files or strings.
"""

from pydantic import BaseModel, Field, ImportString
from typing import TYPE_CHECKING, Any, Annotated
from collections.abc import Mapping, Sequence, Iterable

if TYPE_CHECKING:
    from ..thing import Thing


class ThingConfig(BaseModel):
    """A Pydantic model corresponding to the `.ThingConfig` dataclass."""

    thing_subclass: ImportString
    """The `.Thing` subclass to add to the server."""

    args: Sequence[Any] | None = None
    r"""Positional arguments to pass to the constructor of ``thing_subclass``\ ."""

    kwargs: Mapping[str, Any] | None = None
    r"""Keyword arguments to pass to the constructor of ``thing_subclass``\ ."""

    thing_connections: Mapping[str, str | Iterable[str] | None] | None = None
    r"""A mapping that sets up the `.thing_slot`\ s.
    Keys are the names of attributes of the `.Thing` and the values are
    the name(s) of the `.Thing`\ (s) you'd like to connect. If this is left
    at its default, the connections will use their default behaviour, usually
    automatically connecting to a `.Thing` of the right type.
    """


ThingName = Annotated[
    str,
    Field(min_length=1, pattern=r"^([a-zA-Z0-9\-_]+)$"),
]


ThingsConfig = Mapping[ThingName, ThingConfig | type[Thing]]


class ThingServerConfig(BaseModel):
    r"""The configuration parameters for a `.ThingServer`\ ."""

    things: ThingsConfig
    """A mapping of names to Thing configurations.
    
    Each Thing on the server must be given a name, which is the dictionary
    key. The value is either the class to be used, or a `.ThingConfig`
    object specifying the class, initial arguments, and other settings.
    """

    settings_folder: str | None = None
    """The location of the settings folder, or `None` to use the default location."""
