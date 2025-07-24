"""A submodule for custom LabThings-FastAPI Exceptions."""

import inspect

# The "import x as x" syntax means symbols are interpreted as being re-exported,
# so they won't be flagged as unused by the linter.
# An __all__ for this module is less than helpful, unless we have an
# automated check that everything's included.
from .dependencies.invocation import (
    InvocationCancelledError as InvocationCancelledError,
)


class DocstringToMessage:
    """A mixin to put Exception docstrings in as their default message."""

    append_to_message: bool = True

    def __init__(self, message: str | None):
        """Initialise an error with a message or its docstring.

        :param message: the optional message.
        """
        doc = inspect.cleandoc(self.__doc__) if self.__doc__ else None
        if message:
            if doc and self.append_to_message:
                super().__init__(message + "\n\n" + doc)
            else:
                super().__init__(message)
        elif doc:
            super().__init__(doc)
        else:
            super().__init__()


class NotConnectedToServerError(DocstringToMessage, RuntimeError):
    """The Thing is not connected to a server.

    This exception is called if a ThingAction is called or
    is a ThingProperty is updated on a Thing that is not
    connected to a ThingServer. A server connection is needed
    to manage asynchronous behaviour.
    """


class ReadOnlyPropertyError(DocstringToMessage, AttributeError):
    """A property is read-only.

    No setter has been defined for this `.FunctionalProperty`, so
    it may not be written to.
    """
