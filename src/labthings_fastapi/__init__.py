r"""LabThings-FastAPI.

This is the top level module for LabThings-FastAPI, a library for building
:ref:`wot_cc` devices using Python. There is documentation on readthedocs_,
and the recommended place to start is :doc:`index`\ .

.. _readthedocs: https://labthings-fastapi.readthedocs.io/

This module contains a number of convenience
imports and is intended to be imported using:

.. code-block:: python

    import labthings_fastapi as lt

The example code elsewhere in the documentation generally follows this
convention. Symbols in the top-level module mostly exist elsewhere in
the package, but should be imported from here as a preference, to ensure
code does not break if modules are rearranged.
"""

from .thing import Thing
from .thing_slots import thing_slot
from .thing_server_interface import ThingServerInterface
from .properties import property, setting, DataProperty, DataSetting
from .actions import action
from .endpoints import fastapi_endpoint
from . import deps
from . import outputs
from .outputs import blob
from .server import ThingServer, cli
from .server.config_model import ThingConfig, ThingServerConfig
from .client import ThingClient
from .invocation_contexts import (
    cancellable_sleep,
    raise_if_cancelled,
    ThreadWithInvocationID,
)

# The symbols in __all__ are part of our public API.
# They are imported when using `import labthings_fastapi as lt`.
# We should check that these symbols stay consistent if modules are rearranged.
# The alternative `from .thing import Thing as Thing` syntax is not used, as
# `mypy` is now happy with the current import style. If other tools prefer the
# re-export style, we may switch in the future.
__all__ = [
    "Thing",
    "ThingServerInterface",
    "property",
    "setting",
    "DataProperty",
    "DataSetting",
    "action",
    "thing_slot",
    "fastapi_endpoint",
    "deps",
    "outputs",
    "blob",
    "ThingServer",
    "cli",
    "ThingConfig",
    "ThingServerConfig",
    "ThingClient",
    "cancellable_sleep",
    "raise_if_cancelled",
    "ThreadWithInvocationID",
]
