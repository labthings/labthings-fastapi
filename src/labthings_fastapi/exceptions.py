"""A submodule for custom LabThings-FastAPI Exceptions"""

from .dependencies.invocation import InvocationCancelledError


class NotConnectedToServerError(RuntimeError):
    """The Thing is not connected to a server

    This exception is called if a ThingAction is called or
    is a ThingProperty is updated on a Thing that is not
    connected to a ThingServer. A server connection is needed
    to manage asynchronous behaviour.
    """


__all__ = ["NotConnectedToServerError", "InvocationCancelledError"]
