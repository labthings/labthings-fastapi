"""Descriptors to add :ref:`wot_affordances` to `.Thing` subclasses.

This module will likely be removed in the next release.
"""

from .action import ActionDescriptor
from .property import ThingProperty
from .property import ThingSetting
from .endpoint import EndpointDescriptor
from .endpoint import HTTPMethod

__all__ = [
    "ActionDescriptor",
    "ThingProperty",
    "ThingSetting",
    "EndpointDescriptor",
    "HTTPMethod",
]
