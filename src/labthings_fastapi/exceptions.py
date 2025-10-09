"""A submodule for custom LabThings-FastAPI Exceptions."""


# An __all__ for this module is less than helpful, unless we have an
# automated check that everything's included.


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


class ThingConnectionError(RuntimeError):
    """A ThingConnection could not be set up.

    This error is raised if the LabThings server is unable to set up a
    ThingConnection, for example because the named Thing does not exist,
    or is of the wrong type, or is not specified and there is no default.
    """


class InvocationCancelledError(BaseException):
    """An invocation was cancelled by the user.

    Note that this inherits from BaseException so won't be caught by
    `except Exception`, it must be handled specifically.

    Action code may want to handle cancellation gracefully. This
    exception should be propagated if the action's status should be
    reported as ``cancelled``, or it may be handled so that the
    action finishes, returns a value, and is marked as ``completed``.

    If this exception is handled and not re-raised, or if it arises in
    a manually-created thread, the action will continue as normal. It
    is a good idea to make sure your action terminates soon after this
    exception is raised.
    """


class InvocationError(RuntimeError):
    """The invocation ended in an anticipated error state.

    When this error is raised, action execution stops as expected. The exception will be
    logged at error level without a traceback, and the invocation will return with
    error status.

    Subclass this error for errors that do not need further traceback information
    to be provided with the error message in logs.
    """


class NoInvocationContextError(RuntimeError):
    """An invocation-specific resource has been requested from outside an invocation.

    This error is raised when the current invocation ID is requested, and there is no
    current invocation ID. Invocation ID is determined from context (using a
    `.ContextVar` ) and is available from within action functions.

    To avoid this error in test code or manually created threads, you should supply
    an invocation context.
    """
