"""A submodule for custom LabThings-FastAPI Exceptions."""


# An __all__ for this module is less than helpful, unless we have an
# automated check that everything's included.


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

    This exception is raised when `~lt.Thing.observe_property` is called with a
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


class PropertyRedefinitionError(AttributeError):
    """A property is being incorrectly redefined.

    This method is raised if a property is at risk of being redefined. This usually
    happens when a decorator is applied to a function with the same name as the
    property. The solution is usually to rename the function.
    """
