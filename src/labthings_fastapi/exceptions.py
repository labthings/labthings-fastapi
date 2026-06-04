"""A submodule for custom LabThings-FastAPI Exceptions."""


# An __all__ for this module is less than helpful, unless we have an
# automated check that everything's included.

from collections.abc import Callable


class NotConnectedToServerError(RuntimeError):
    """The Thing is not connected to a server.

    This exception is called if an Action is called or
    a `~lt.DataProperty` is updated on a Thing that is not
    connected to a ThingServer.

    A server connection is needed to manage asynchronous behaviour.

    `~lt.Thing` instances are also only assigned a ``path`` when they
    are added to a server, so this error may be raised by functions
    that implement the HTTP API if an attempt is made to construct
    the API before the `~lt.Thing` has been assigned a path.
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

    This exception is raised when trying to observe a
    property that is not observable. Currently, only data properties are
    observable: functional properties (using a getter/setter) may not be
    observed.
    """


class InconsistentTypeError(TypeError):
    """Different type hints have been given for a descriptor.

    Some descriptors in LabThings, particularly `~lt.DataProperty` and `.ThingSlot`
    may have their type specified in different ways. If multiple type hints are
    provided, they must match. See `~lt.property` for more details.
    """


class MissingTypeError(TypeError):
    """No type hints have been given for a descriptor that requires a type.

    Every property and thing connection should have a type hint,
    There are different ways of providing these type hints.
    This error indicates that no type hint was found.

    See documentation for `~lt.property` and `~lt.thing_slot` for more details.
    """


class DescriptorNotAddedToClassError(RuntimeError):
    """Descriptor has not yet been added to a class.

    This error is raised if certain properties of descriptors are accessed
    before ``__set_name__`` has been called on the descriptor.  ``__set_name__``
    is part of the descriptor protocol, and is called when a class is defined
    to notify the descriptor of its name and owning class.

    If you see this error, it often means that a descriptor has been instantiated
    but not attached to a class, for example:

    .. code-block:: python

        import labthings as lt


        class Test(lt.Thing):
            myprop: int = lt.property(default=0)  # This is OK


        orphaned_prop: int = lt.property(default=0)  # Not OK

        Test.myprop.model  # Evaluates to a pydantic model

        orphaned_prop.model  # Raises this exception
    """


class UnexpectedGarbageCollectionError(RuntimeError):
    """An object was garbage collected unexpectedly.

    This error is raised when a weak reference fails to resolve unexpectedly.
    It usually means an object (often a class) has been deleted, while a weak reference
    to it is still held somewhere. This is done, for example, by `BaseDescriptor`
    holding a weak reference to the owning class.

    It is hard to imagine a situation where the class would be deleted while the
    descriptor object remains accessible, but this error exists for that state.
    """


class DescriptorAddedToClassTwiceError(RuntimeError):
    """A Descriptor has been added to a class more than once.

    This error is raised if ``__set_name__`` is called more than once on a
    descriptor. This happens when either the same descriptor instance is
    used twice in one class definition, or if a descriptor instance is used
    on more than one class.

    .. note::

        `.FunctionalProperty` includes a special case that will ignore the
        ``__set_name__`` call corresponding to the setter. This allows the
        property to be defined like ``prop4`` below, even though it does
        assign the descriptor to two names. That behaviour is specific to
        `.FunctionalProperty` and `.FunctionalSetting` and is not part of
        `.BaseDescriptor` because `.BaseDescriptor` has no setter.

        ``mypy`` does not allow custom property-like descriptors to follow the
        syntax used by the built-in ``property`` of giving both the getter and
        setter functions the same name: this causes an error because it is
        a redefinition. We suggest using a different name for the setter to
        work around this, hence the need for an exception.

    .. code-block:: python

        class MyDescriptor(BaseDescriptor):
            "An example descriptor that inherits from BaseDescriptor."

            def __init__(getter=None):
                "Initialise the descriptor, allowing use as a decorator."
                self._getter = getter

            def setter(self, setter):
                "Add a setter to the descriptor."
                self._setter = setter
                return self


        class Example:
            "An example class with descriptors."

            # prop1 is fine - only used once.
            prop1 = MyDescriptor()

            # prop2 reuses the name ``prop2`` which may confuse ``mypy`` but
            # will only call ``__set_name__`` once.
            @MyDescriptor
            def prop2(self):
                "A dummy property"
                return False

            @prop2.setter
            def prop2(self, val):
                "Set the dummy property"
                pass

            # prop3a and prop3b will cause this error
            prop3a = MyDescriptor()
            prop3b = MyDescriptor()

            # prop4 and set_prop4 will cause this error on BaseDescriptor
            # but there is a specific exception in FunctionalProperty
            # to allow this form.
            @MyDescriptor
            def prop4(self):
                "An example property with two names"
                return True

            @prop4.setter
            def _set_prop4(self, val):
                "A setter for prop4 that is not named prop4."
                pass

    .. note::

        Because this exception is raised in ``__set_name__`` it will not
        appear to come from the descriptor assignment, but instead it will
        be raised at the end of the class definition. The descriptor name(s)
        should be in the error message.

    """


class ThingNotConnectedError(RuntimeError):
    r"""`.ThingSlot`\ s have not yet been set up.

    This error is raised if a `.ThingSlot` is accessed before the `~lt.Thing` has
    been supplied by the LabThings server. This usually happens because either
    the `~lt.Thing` is being used without a server (in which case the attribute
    should be mocked), or because it has been accessed before ``__enter__``
    has been called.
    """


class ThingSlotError(RuntimeError):
    """A `.ThingSlot` could not be set up.

    This error is raised if the LabThings server is unable to set up a
    `.ThingSlot`, for example because the named Thing does not exist,
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


class CausedByUserCodeError(Exception):
    """A mixin to allow exceptions to refer to downstream code."""

    def _append_to_args(self, message: str) -> None:
        """Add a message to the exception's arguments.

        The message will be appended to the first (and usually only) argument.
        If the first argument isn't a string, we'll append another argument with the
        message.

        If there's no argument, or the argument is an empty string, it will be replaced
        by the message.

        :param message: the message to append.
        """
        # The line below ensures () and ("", ) are treated equivalently.
        first_arg = self.args[0] if len(self.args) > 0 else ""
        if isinstance(first_arg, str):
            if len(first_arg) > 0:
                first_arg += "\n"
            # Note: the second term is an empty tuple if len(self.args) < 2
            self.args = (first_arg + message,) + self.args[1:]
        else:
            self.args += (message,)

    def set_source_function(self, func: Callable) -> None:
        """Add the location of a user-supplied function to the error message.

        :param func: the function that caused this error.
        """
        code = func.__code__
        self._append_to_args(
            f"This was likely caused by function '{code.co_name}' "
            f"at {code.co_filename}:{code.co_firstlineno}"
        )

    def set_source_class(self, cls: type, attr: str | None = None) -> None:
        """Add a reference to a class (and optionally attribute).

        :param cls: the class that caused this error.
        :param attr: the attribute name that caused this error.
        """
        name = f"{cls.__module__}.{cls.__qualname__}"
        if attr:
            name += f".{attr}"
        self._append_to_args(f"\nThis was likely caused by '{name}'.")


class InvalidReturnValueError(CausedByUserCodeError, RuntimeError):
    r"""The return value from a method cannot be serialised by LabThings.

    This error is raised when an action returns a value that can't be serialised.
    This usually means that either it doesn't match the declared return type of
    the function, or the declared return type permits un-serialisable values.

    If an action's return type is missing or `Any`\ , it's possible to return a
    value that can't be serialised, which will cause this error.

    The solution is usually to ensure that the return type of your action is
    either a simple type that can be serialised to JSON, or a Pydantic model.
    You should also check that the function's return value matches the declared
    type, ideally by regularly running a type checker like `mypy` on your code.
    """


class UnserialisableTypeError(CausedByUserCodeError, TypeError):
    r"""A type has been specified that can't be serialised to JSON.

    This error generally means a property or action has a type that cannot be
    serialised to JSON. This might be an instance of a custom class, or another
    datatype that doesn't have a ready representation using JSON-compatible types.

    This error can often be fixed using `pydantic` annotations, or by using simple
    Python types instead of custom ones.
    """


class LogConfigurationError(RuntimeError):
    """There is a problem with logging configuration.

    LabThings uses the `logging` module to collect logs from actions. This requires
    certain handlers and filters to be set up. This exception is raised if they
    cannot be added, or if they are not present when they are needed.
    """


class NoBlobManagerError(RuntimeError):
    """Raised if an API route accesses Invocation outputs without a BlobIOContextDep.

    Any access to an invocation output must have BlobIOContextDep as a dependency, as
    the output may be a blob, and the blob needs this context to resolve its URL.
    """


class NoUrlForContextError(RuntimeError):
    """Raised if URLFor is serialised without a url_for context variable being set.

    This usually indicates that URLFor is being serialised somewhere other than in
    an HTTP response,
    for example in test code or in a background task. In these cases, you should
    set up the url_for context variable manually, for example using the
    `.testing.use_dummy_url_for` context manager.
    """


class UnsupportedConstraintError(ValueError):
    """A constraint argument is not supported.

    This exception is raised when a constraint argument is passed to
    a property that is not in the supported list. See
    `labthings_fastapi.properties.CONSTRAINT_ARGS` for the list of
    supported arguments. Their meaning is described in the `pydantic.Field`
    documentation.
    """


class FailedToInvokeActionError(RuntimeError):
    """The action could not be started.

    This error is raised by a `~lt.ThingClient` instance if an action could not be
    started.
    It most commonly occurs because the input to the action could not be converted
    to the required type: the error message should give more detail on what's wrong.
    """


class ServerActionError(RuntimeError):
    """The action ended with an error on the server.

    This error is raised by a `ThingClient` when an action is successfully invoked on
    the server, but does not complete. The error message should include more information
    on why this happened.
    """


class ClientPropertyError(RuntimeError):
    """Setting or getting a property via a ThingClient failed."""


class NotBoundToInstanceError(RuntimeError):
    """A `.BaseDescriptorInfo` is not bound to an object.

    Some methods and properties of `.BaseDescriptorInfo` objects require them
    to be bound to a `~lt.Thing` instance. If these methods are called on a
    `.BaseDescriptorInfo` object that is unbound, this exception is raised.

    This exception should only be seen when `.BaseDescriptorInfo` objects are
    generated from a `~lt.Thing` class. Usually, they should be accessed via a
    `~lt.Thing` instance, in which case they will be bound.
    """


class FeatureNotAvailableError(NotImplementedError):
    """A feature is not available.

    There are some methods provided by base classes where implementation is optional.
    These methods raise `FeatureNotAvailableError` if they are not implemented.

    Currently this is done for the default value of properties, and their reset
    method.
    """


class InvalidClassSettingsError(ValueError):
    """A Thing's class settings are not valid.

    This error is raised when the ``_class_settings`` attribute of a `Thing` subclass
    is not valid.
    """


class FeatureNotEnabledError(RuntimeError):
    """A feature is being used that is currently disabled.

    Some new or optional features must be enabled in the server settings or in
    `~lt.Thing._class_settings` before they can be used.
    This error is raised if a feature is used when it is not enabled.
    """


class PropertyRedefinitionError(AttributeError):
    """A property is being incorrectly redefined.

    This method is raised if a property is at risk of being redefined. This usually
    happens when a decorator is applied to a function with the same name as the
    property. The solution is usually to rename the function.
    """


class DefaultWillChangeWarning(DeprecationWarning):
    """A default value will change in a future release.

    A default value will change in the future. This warning can usually be eliminated
    by setting the value explicitly.
    """


class GlobalLockBusyError(TimeoutError):
    """The global lock is already in use.

    This exception is raised when code needs the global lock but cannot acquire
    it. It indicates that the LabThings server is busy running another action or
    property setter.
    """


class MessageDroppedWarning(RuntimeWarning):
    """A message was dropped by the message broker.

    This warning is emitted when a message can't be sent to a subscribed stream
    because the stream's buffer is full. The message broker won't block, as
    doing so could result in a potentially infinite number of stalled tasks.

    If you see this warning, it means that a stream has been subscribed to
    messages, but is not being read. Most likely, this means the stream was
    not closed or deleted properly.
    """
