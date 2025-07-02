"""
FastAPI dependencies for LabThings.

The symbols in this module are type annotations that can be used in
the arguments of Action methods (or FastAPI endpoints) to
automatically supply the required dependencies.

See the documentation on dependencies for more details of how to use
these.
"""

from .dependencies.blocking_portal import BlockingPortal
from .dependencies.invocation import InvocationID, InvocationLogger, CancelHook
from .dependencies.metadata import GetThingStates
from .dependencies.raw_thing import raw_thing_dependency
from .dependencies.thing import direct_thing_client_dependency

# The symbols in __all__ are part of our public API. See note
# in src/labthings_fastapi/__init__.py for more details.
__all__ = [
    "BlockingPortal",
    "InvocationID",
    "InvocationLogger",
    "CancelHook",
    "GetThingStates",
    "raw_thing_dependency",
    "direct_thing_client_dependency",
]
