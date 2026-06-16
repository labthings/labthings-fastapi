"""Log-related functions and classes.

This module currently contains code that allows us to filter out logs by invocaton
ID, so that they may be returned when invocations are queried.

It also defines the `USER` loglevel, which should be used for messages that are
intended to be visible to the user in e.g. a graphical interface.
"""

import logging
from collections.abc import MutableSequence
from typing import Any
from uuid import UUID
from weakref import WeakValueDictionary

from labthings_fastapi.exceptions import LogConfigurationError, NoInvocationContextError
from labthings_fastapi.invocation_contexts import get_invocation_id

# Add the custom USER loglevel.
USER = logging.INFO + 5
logging.addLevelName(USER, "USER")


class LoggerWithUser(logging.getLoggerClass()):
    """A subclass of `logging.Logger` with an extra `user` level."""

    def user(self, msg: str, *args: Any, **kwargs: Any) -> None:
        r"""Log 'msg % args' with severity 'INFO'.

        To pass exception information, use the keyword argument exc_info with
        a true value, e.g.

        .. code-block:: python

            logger.info("Houston, we have a %s", "interesting problem", exc_info=1)

        :param msg: The message to log, including `%` placeholders if desired.
        :param \*args: Additional arguments can be used to customise ``msg``\ .
        :param \**kwargs: Keyword arguments may be used to customise ``msg``\ .
        """
        if self.isEnabledFor(USER):
            self._log(USER, msg, args, **kwargs)


# We tell `logging` to use our new class, so `user` is available to all
# loggers obtained with `logging.getLogger`
# We do this before defining THING_LOGGER so that it gets the new level
logging.setLoggerClass(LoggerWithUser)


# Note that this is done **after** defining the new level, so that it's
# of the correct class.
THING_LOGGER = logging.getLogger("labthings_fastapi.things")


def get_thing_logger() -> LoggerWithUser:
    """Return the Thing Logger.

    `lt.Thing.logger` will return a child of this logger, and any messages
    logged to this logger will be picked up by invocation logs, if they are
    logged from an invocation thread/context.

    :return: the parent logger of all the `lt.Thing.logger` instances.
    :raises TypeError: if the logger is missing the ``user`` level.
    """
    if not isinstance(THING_LOGGER, LoggerWithUser):
        raise TypeError("Customisations to `logging.Logger` have been lost.")
    return THING_LOGGER


def inject_invocation_id(record: logging.LogRecord) -> bool:
    r"""Add the invocation ID to records.

    This function adds the current invocation ID to log records. If it is not
    available, we set the record's ``invocation_id`` property to `None`\ .

    :param record: the `logging.LogRecord` object to modify.

    :return: `True` (which signals we should keep every record if this is used
        as a filter).
    """
    try:
        id = get_invocation_id()
        record.invocation_id = id
    except NoInvocationContextError:
        record.invocation_id = None
    return True


class DequeByInvocationIDHandler(logging.Handler):
    """A log handler that stores entries in memory."""

    def __init__(
        self,
        level: int = logging.NOTSET,
    ) -> None:
        """Set up a log handler that appends messages to a deque.

        .. warning::
            This log handler does not currently rotate or truncate
            the list. It's best to use a `deque` with a finite capacity
            to avoid memory leaks.

        :param level: sets the level of the handler. Usually
            a log level of `logging.NOTSET` is appropriate. This does not
            do any extra filtering, and so will use the log level of the
            logger to which it is attached.
        """
        super().__init__()
        self.setLevel(level)
        self.destinations = WeakValueDictionary[UUID, MutableSequence]()
        self.addFilter(inject_invocation_id)

    def add_destination_for_id(self, id: UUID, destination: MutableSequence) -> None:
        """Append logs matching ``id`` to a specified sequence.

        :param id: the ``invocation_id`` to match.
        :param destination: should specify a deque, to which we will append
            each log entry as it comes in. This is assumed to be thread
            safe.
        """
        self.destinations[id] = destination

    def emit(self, record: logging.LogRecord) -> None:
        """Save a log record to the destination deque.

        :param record: the `logging.LogRecord` object to add.
        """
        id = getattr(record, "invocation_id", None)
        if isinstance(id, UUID):
            try:
                self.destinations[id].append(record)
            except KeyError:
                pass  # If there's no destination for a particular log, ignore it.


def configure_thing_logger(level: int | None = None) -> None:
    """Set up the logger for thing instances.

    We always set the logger for thing instances to level INFO by default,
    as this is currently used to relay progress to the client.

    This function will collect logs on a per-invocation
    basis by adding a `.DequeByInvocationIDHandler` to the log. Only one
    such handler will be added - subsequent calls are ignored.

    Unfortunately, filters must be added to every sub-logger, so globally adding
    a filter to add invocation ID is not possible. Instead, we attach a filter to
    the handler, which filters all the records that propagate to it (i.e. anything
    that starts with ``labthings_fastapi.things``).

    :param level: the logging level to use. If not specified, we use INFO.
    """
    if level is not None:
        THING_LOGGER.setLevel(level)
    else:
        THING_LOGGER.setLevel(logging.INFO)

    if not any(
        isinstance(h, DequeByInvocationIDHandler) for h in THING_LOGGER.handlers
    ):
        THING_LOGGER.addHandler(DequeByInvocationIDHandler())


def add_thing_log_destination(
    invocation_id: UUID, destination: MutableSequence
) -> None:
    """Append logs matching ``invocation_id`` to a specified sequence.

    This instructs a handler on the logger used for `~lt.Thing` instances to append a
    copy of the logs generated by that invocation to the specified sequence.
    This is primarily used by invocation threads to collect their logs, so they
    may be returned when the invocation is queried.

    :param invocation_id: the ``invocation_id`` to match.
    :param destination: should specify a deque, to which we will append
        each log entry as it comes in. This is assumed to be thread
        safe.
    :raises LogConfigurationError: if there is not exactly one suitable handler.
    """
    handlers = [
        h for h in THING_LOGGER.handlers if isinstance(h, DequeByInvocationIDHandler)
    ]
    if len(handlers) != 1:
        if len(handlers) == 0:
            msg = "There is no suitable handler on {THING_LOGGER}."
        else:
            msg = "There were multiple matching handlers on {THING_LOGGER}, "
            msg += "which should not happen: this is a LabThings bug."
        raise LogConfigurationError(msg)
    handler = handlers[0]
    handler.add_destination_for_id(invocation_id, destination)
