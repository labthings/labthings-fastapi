"""A submodule for custom LabThings-FastAPI Exceptions."""

# The "import x as x" syntax means symbols are interpreted as being re-exported,
# so they won't be flagged as unused by the linter.
# An __all__ for this module is less than helpful, unless we have an
# automated check that everything's included.
from .dependencies.invocation import (
    InvocationCancelledError as InvocationCancelledError,
)
from .dependencies.invocation import InvocationError as InvocationError


class NotConnectedToServerError(RuntimeError):
    """The Thing is not connected to a server.

    This exception is called if an Action is called or
    a `.DataProperty` is updated on a Thing that is not
    connected to a ThingServer. A server connection is needed
    to manage asynchronous behaviour.
    """


class ServerNotRunningError(RuntimeError):
    """The ThingServer is not running.
    
    This exception is called when a function assumes the ThingServer is
    running, and it is not. This might be because the function needs to call
    code in the async event loop.
    """


class ReadOnlyPropertyError(AttributeError):
    """A property is read-only.

    No setter has been defined for this `.FunctionalProperty`, so
    it may not be written to.
    """


class PropertyNotObservableError(RuntimeError):
    """The property is not observable.

    This exception is raised when `.Thing.observe_property` is called with a
    property that is not observable. Currently, only data properties are
    observable: functional properties (using a getter/setter) may not be
    observed.
    """
