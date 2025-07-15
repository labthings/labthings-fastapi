"""Descriptors to add wot_affordances_ to `.Thing` subclasses.

This module will likely be removed in the next release.
"""

from .action import ActionDescriptor as ActionDescriptor
from .property import ThingProperty as ThingProperty
from .property import ThingSetting as ThingSetting
from .endpoint import EndpointDescriptor as EndpointDescriptor
from .endpoint import HTTPMethod as HTTPMethod
