"""A submodule for custom LabThings-FastAPI Exceptions."""

# The "import x as x" syntax means symbols are interpreted as being re-exported,
# so they won't be flagged as unused by the linter.
# An __all__ for this module is less than helpful, unless we have an
# automated check that everything's included.
from .dependencies.invocation import (
    InvocationCancelledError as InvocationCancelledError,
)


class NotConnectedToServerError(RuntimeError):
    """The Thing is not connected to a server.

    This exception is called if an Action is called or
    a `.DataProperty` is updated on a Thing that is not
    connected to a ThingServer. A server connection is needed
    to manage asynchronous behaviour.
    """


class ReadOnlyPropertyError(AttributeError):
    """A property is read-only.

    No setter has been defined for this `.FunctionalProperty`, so
    it may not be written to.
    """
