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
    connected to a ThingServer.

    A server connection is needed to manage asynchronous behaviour.

    `.Thing` instances are also only assigned a ``path`` when they
    are added to a server, so this error may be raised by functions
    that implement the HTTP API if an attempt is made to construct
    the API before the `.Thing` has been assigned a path.
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


class InconsistentTypeError(TypeError):
    """Different type hints have been given for a descriptor.

    Some descriptors in LabThings, particularly `.DataProperty` and `.ThingConnection`
    may have their type specified in different ways. If multiple type hints are
    provided, they must match. See `.property` for more details.
    """


class MissingTypeError(TypeError):
    """No type hints have been given for a descriptor that requires a type.

    Every property and thing connection should have a type hint,
    There are different ways of providing these type hints.
    This error indicates that no type hint was found.

    See documentation for `.property` and `.thing_connection` for more details.
    """


class ThingNotConnectedError(RuntimeError):
    """ThingConnections have not yet been set up.

    This error is raised if a ThingConnection is accessed before the `.Thing` has
    been supplied by the LabThings server. This usually happens because either
    the `.Thing` is being used without a server (in which case the attribute
    should be mocked), or because it has been accessed before ``__enter__``
    has been called.
    """
