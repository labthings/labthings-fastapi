"""Actions module.

:ref:`wot_actions` are represented by methods, decorated with the `.thing_action`
decorator.

See the :ref:`actions` documentation for a top-level overview of actions in
LabThings-FastAPI.

Developer notes
---------------

Currently much of the code related to Actions is in `.thing_action` and the
underlying `.ActionDescriptor`. This is likely to be refactored in the near
future.
"""

from __future__ import annotations
import datetime
import logging
from collections import deque
from threading import Thread, Lock
from typing import MutableSequence, Optional, Any
import uuid
from typing import TYPE_CHECKING
import weakref
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from ..utilities import model_to_dict
from ..utilities.introspection import EmptyInput
from ..thing_description._model import LinkElement
from .invocation_model import InvocationModel, InvocationStatus, LogRecordModel
from ..dependencies.invocation import (
    CancelHook,
    InvocationCancelledError,
    InvocationError,
    invocation_logger,
)
from ..outputs.blob import BlobIOContextDep, blobdata_to_url_ctx

if TYPE_CHECKING:
    # We only need these imports for type hints, so this avoids circular imports.
    from ..descriptors import ActionDescriptor
    from ..thing import Thing

ACTION_INVOCATIONS_PATH = "/action_invocations"
"""The API route used to list `.Invocation` objects."""


class NoBlobManagerError(RuntimeError):
    """Raised if an API route accesses Invocation outputs without a BlobIOContextDep.

    Any access to an invocation output must have BlobIOContextDep as a dependency, as
    the output may be a blob, and the blob needs this context to resolve its URL.
    """


class Invocation(Thread):
    """A Thread subclass that retains output values and tracks progress.

    `.Invocation` threads add several bits of functionality compared to the base
    `threading.Thread`.

    * They are instantiated with an `.ActionDescriptor` and a `.Thing`
      rather than a target function (see ``__init__``).
    * Each invocation is assigned a unique ``ID`` to allow it to be polled
      over HTTP.
    * A `.CancelHook` is provided to allow the invocation to stop gracefully
      if it is cancelled by the user.
    """

    def __init__(
        self,
        action: ActionDescriptor,
        thing: Thing,
        id: uuid.UUID,
        input: Optional[BaseModel] = None,
        dependencies: Optional[dict[str, Any]] = None,
        log_len: int = 1000,
        cancel_hook: Optional[CancelHook] = None,
    ) -> None:
        """Create a thread to run an action and track its outputs.

        :param action: provides the function that we run, as well as metadata
            and type information. The descriptor is not bound to an object, so we
            supply the `.Thing` it's bound to when the function is run.
        :param thing: is the object on which we are running the ``action``, i.e.
            it is supplied to the function wrapped by ``action`` as the ``self``
            argument.
        :param id: is a `uuid.UUID` used to identify the invocation, for example
            when polling its status via HTTP.
        :param input: is a `pydantic.BaseModel` representing the body of the HTTP
            request that invoked the action. It is supplied to the function as
            keyword arguments.
        :param dependencies: is a dictionary of keyword arguments, supplied by
            FastAPI by its dependency injection mechanism.
        :param log_len: sets the number of log entries that will be held in
            memory by the invocation's logger.
        :param cancel_hook: is a `threading.Event` subclass that tells the
            invocation it's time to stop. See `.CancelHook`.
        """
        Thread.__init__(self, daemon=True)

        # keep track of the corresponding ActionDescriptor
        self.action_ref = weakref.ref(action)
        self.thing_ref = weakref.ref(thing)
        self.input = input if input is not None else EmptyInput()
        self.dependencies = dependencies if dependencies is not None else {}
        self.cancel_hook = cancel_hook

        # A UUID for the Invocation (not the same as the threading.Thread ident)
        self._ID = id  # Task ID

        # How long to keep the invocation after it finishes
        self.retention_time = action.retention_time
        self.expiry_time: Optional[datetime.datetime] = None

        # Private state properties
        self._status_lock = Lock()  # This Lock protects properties below
        self._status: InvocationStatus = InvocationStatus.PENDING  # Task status
        self._return_value: Optional[Any] = None  # Return value
        self._request_time: datetime.datetime = datetime.datetime.now()
        self._start_time: Optional[datetime.datetime] = None  # Task start time
        self._end_time: Optional[datetime.datetime] = None  # Task end time
        self._exception: Optional[Exception] = None  # Propagate exceptions helpfully
        self._log: deque = deque(maxlen=log_len)  # log entries for this thread

    @property
    def id(self) -> uuid.UUID:
        """UUID for the thread. Note this not the same as the native thread ident."""
        return self._ID

    @property
    def output(self) -> Any:
        """Return value of the Action. If the Action is still running, returns None.

        :raise NoBlobManagerError: If this is called in a context where the blob
            manager context variables are not available. This stops errors being raised
            later once the blob is returned and tries to serialise. If the errors
            happen during serialisation the stack-trace will not clearly identify
            the route with the missing dependency.
        """
        try:
            blobdata_to_url_ctx.get()
        except LookupError as e:
            raise NoBlobManagerError(
                "An invocation output has been requested from a api route that "
                "doesn't have a BlobIOContextDep dependency. This dependency is needed "
                " for blobs to identify their url."
            ) from e

        with self._status_lock:
            return self._return_value

    @property
    def log(self) -> list[LogRecordModel]:
        """A list of log items generated by the Action."""
        with self._status_lock:
            return list(self._log)

    @property
    def status(self) -> InvocationStatus:
        """Current running status of the thread.

        See `.InvocationStatus` for the values and their meanings.
        """
        with self._status_lock:
            return self._status

    @property
    def action(self) -> ActionDescriptor:
        """The `.ActionDescriptor` object running in this thread."""
        action = self.action_ref()
        assert action is not None, "The action for an `Invocation` has been deleted!"
        return action

    @property
    def thing(self) -> Thing:
        """The `.Thing` to which the action is bound, i.e. this is ``self``."""
        thing = self.thing_ref()
        assert thing is not None, "The `Thing` on which an action was run is missing!"
        return thing

    def cancel(self) -> None:
        """Cancel the task by requesting the code to stop.

        This is an opt-in feature: the action must use
        a `.CancelHook` dependency and periodically check it.
        """
        if self.cancel_hook is not None:
            self.cancel_hook.set()

    def response(self, request: Optional[Request] = None) -> InvocationModel:
        """Generate a representation of the invocation suitable for HTTP.

        When an invocation is polled, we return a JSON object that includes
        its status, any log entries, a return value (if completed), and a link
        to poll for updates.

        :param request: is used to generate the ``href`` in the response, which
            should retrieve an updated version of this response.

        :return: an `.InvocationModel` representing this `.Invocation`.
        """
        if request:
            href = str(request.url_for("action_invocation", id=self.id))
        else:
            href = f"{ACTION_INVOCATIONS_PATH}/{self.id}"
        links = [
            LinkElement(rel="self", href=href),
            LinkElement(rel="output", href=href + "/output"),
        ]
        # The line below confuses MyPy because self.action **evaluates to** a Descriptor
        # object (i.e. we don't call __get__ on the descriptor).
        return self.action.invocation_model(  # type: ignore[call-overload]
            status=self.status,
            id=self.id,
            action=self.thing.path + self.action.name,  # type: ignore[call-overload]
            href=href,
            timeStarted=self._start_time,
            timeCompleted=self._end_time,
            timeRequested=self._request_time,
            input=self.input,
            output=self.output,
            links=links,
            log=self.log,
        )

    def run(self) -> None:
        """Run the action and track progress.

        `.Invocation` overrides the default `threading.Thread.run` method to
        add ways to track its progress and capture the return value.

        The code to be run is the function wrapped in the `.ActionDescriptor`
        that is passed in as ``action``. Its arguments are the associated
        `.Thing` (the first argument, i.e. ``self``), the ``input`` model
        (split into keyword arguments for each field), and any ``dependencies``
        (also as keyword arguments).

        We update the status of the action by setting ``self._status`` and
        emitting a changed event. This runs async code in the event loop that
        informs any clients listening over websockets that the event's status
        has changed.

        Logs are retained by a custom log handler, and are included when the
        `.Invocation` is serialised over HTTP.

        If exceptions are raised by the action code, these are caught and
        stored. The status is then set to ERROR and the thread terminates.

        See `.Invocation.status` for status values.
        """
        # self.action evaluates to an ActionDescriptor. This confuses mypy,
        # which thinks we are calling ActionDescriptor.__get__.
        action: ActionDescriptor = self.action  # type: ignore[call-overload]
        try:
            action.emit_changed_event(self.thing, self._status.value)

            # Capture just this thread's log messages
            handler = DequeLogHandler(dest=self._log)
            logger = invocation_logger(self.id)
            logger.addHandler(handler)

            thing = self.thing
            kwargs = model_to_dict(self.input)
            assert thing is not None

            with self._status_lock:
                self._status = InvocationStatus.RUNNING
                self._start_time = datetime.datetime.now()
                action.emit_changed_event(self.thing, self._status.value)

            # The next line actually runs the action.
            ret = action.__get__(thing)(**kwargs, **self.dependencies)

            with self._status_lock:
                self._return_value = ret
                self._status = InvocationStatus.COMPLETED
                action.emit_changed_event(self.thing, self._status.value)
        except InvocationCancelledError:
            logger.info(f"Invocation {self.id} was cancelled.")
            with self._status_lock:
                self._status = InvocationStatus.CANCELLED
                action.emit_changed_event(self.thing, self._status.value)
        except Exception as e:  # skipcq: PYL-W0703
            # First log
            if isinstance(e, InvocationError):
                # Log without traceback
                logger.error(e)
            else:
                logger.exception(e)
            # Then set status
            with self._status_lock:
                self._status = InvocationStatus.ERROR
                self._exception = e
                action.emit_changed_event(self.thing, self._status.value)
        finally:
            with self._status_lock:
                self._end_time = datetime.datetime.now()
                self.expiry_time = self._end_time + datetime.timedelta(
                    seconds=self.retention_time,
                )
            logger.removeHandler(handler)  # Stop saving logs
            # If we don't remove the log handler, it's a circular ref/memory leak.


class DequeLogHandler(logging.Handler):
    """A log handler that stores entries in memory."""

    def __init__(
        self,
        dest: MutableSequence,
        level: int = logging.INFO,
    ) -> None:
        """Set up a log handler that appends messages to a deque.

        .. warning::
            This log handler does not currently rotate or truncate
            the list - so if you use it on a thread that produces a
            lot of log messages, you may run into memory problems.

            Using a `.deque` with a finite capacity helps to mitigate
            this.

        :param dest: should specify a deque, to which we will append
            each log entry as it comes in. This is assumed to be thread
            safe.
        :param level: sets the level of the logger. For most invocations,
            a log level of `logging.INFO` is appropriate.
        """
        logging.Handler.__init__(self)
        self.setLevel(level)
        self.dest = dest

    def emit(self, record: logging.LogRecord) -> None:
        """Save a log record to the destination deque.

        :param record: the `logging.LogRecord` object to add.
        """
        self.dest.append(record)


class ActionManager:
    """A class to manage a collection of actions."""

    def __init__(self) -> None:
        """Set up an `.ActionManager`."""
        self._invocations: dict[uuid.UUID, Invocation] = {}
        self._invocations_lock = Lock()

    @property
    def invocations(self) -> list[Invocation]:
        """A list of all the `.Invocation` objects running or recently completed."""
        with self._invocations_lock:
            return list(self._invocations.values())

    def append_invocation(self, invocation: Invocation) -> None:
        """Add an `.Invocation` to the `.ActionManager`.

        :param invocation: The `.Invocation` to add.
        """
        with self._invocations_lock:
            self._invocations[invocation.id] = invocation

    def invoke_action(
        self,
        action: ActionDescriptor,
        thing: Thing,
        id: uuid.UUID,
        input: Any,
        dependencies: dict[str, Any],
        cancel_hook: CancelHook,
    ) -> Invocation:
        """Invoke an action, returning the thread where it's running.

        See `.Invocation` for more details.

        :param action: provides the function that we run, as well as metadata
            and type information. The descriptor is not bound to an object, so we
            supply the `.Thing` it's bound to when the function is run.
        :param thing: is the object on which we are running the ``action``, i.e.
            it is supplied to the function wrapped by ``action`` as the ``self``
            argument.
        :param id: is a `uuid.UUID` used to identify the invocation, for example
            when polling its status via HTTP.
        :param input: is a `pydantic.BaseModel` representing the body of the HTTP
            request that invoked the action. It is supplied to the function as
            keyword arguments.
        :param dependencies: is a dictionary of keyword arguments, supplied by
            FastAPI by its dependency injection mechanism.
        :param cancel_hook: is a `threading.Event` subclass that tells the
            invocation it's time to stop. See `.CancelHook`.

        :return: an `.Invocation` object that has been started.
        """
        thread = Invocation(
            action=action,
            thing=thing,
            input=input,
            dependencies=dependencies,
            id=id,
            cancel_hook=cancel_hook,
        )
        self.append_invocation(thread)
        thread.start()
        return thread

    def get_invocation(self, id: uuid.UUID) -> Invocation:
        """Retrieve an invocation by ID.

        :param id: the unique ID of the action to retrieve.
        :return: the `.Invocation` object.
        """
        with self._invocations_lock:
            return self._invocations[id]

    def list_invocations(
        self,
        action: Optional[ActionDescriptor] = None,
        thing: Optional[Thing] = None,
        request: Optional[Request] = None,
    ) -> list[InvocationModel]:
        """All of the invocations currently managed.

        Returns a list of `.InvocationModel` instances representing all the
        invocations that are currently running, or have recently completed and
        not yet expired.

        :param action: filters out only the invocations of a particular
            `.ActionDescriptor`. Note that if there are two Things
            of the same subclass, filtering by action will return invocations
            on either `.Thing`.
        :param thing: returns only invocations of actions on a particular `.Thing`.
            This will often be combined with filtering by ``action`` to give the
            list of invocations returned by a GET request on an action endpoint.
        :param request: is used to pass a `fastapi.Request` object to the
            `.Invocation.response` method. Doing so ensures the URL returned as
            ``href`` in the response matches the address used to communicate with
            the server (i.e. it uses `fastapi.Request.url_for` instead of a path
            generated from a string).

        :return: A list of invocations, optionally filtered by Thing and/or Action.
        """
        return [
            i.response(request=request)
            for i in self.invocations
            if thing is None or i.thing == thing
            if action is None or i.action == action  # type: ignore[call-overload]
            # i.action evaluates to an ActionDescriptor, which confuses mypy - it
            # thinks we are calling ActionDescriptor.__get__ but this isn't ever
            # called.
        ]

    def expire_invocations(self) -> None:
        """Delete invocations that have passed their expiry time."""
        to_delete = []
        with self._invocations_lock:
            for k, v in self._invocations.items():
                if v.expiry_time is not None:
                    if v.expiry_time < datetime.datetime.now():
                        to_delete.append(k)
            logging.debug(f"Deleting invocations {to_delete} as they have expired")
            for k in to_delete:
                del self._invocations[k]

    def attach_to_app(self, app: FastAPI) -> None:
        """Add /action_invocations and /action_invocation/{id} endpoints to FastAPI.

        :param app: The `fastapi.FastAPI` application to which we add the endpoints.
        """

        @app.get(ACTION_INVOCATIONS_PATH, response_model=list[InvocationModel])
        def list_all_invocations(
            request: Request, _blob_manager: BlobIOContextDep
        ) -> list[InvocationModel]:
            return self.list_invocations(request=request)

        @app.get(
            ACTION_INVOCATIONS_PATH + "/{id}",
            response_model=InvocationModel,
            responses={404: {"description": "Invocation ID not found"}},
        )
        def action_invocation(
            id: uuid.UUID, request: Request, _blob_manager: BlobIOContextDep
        ) -> InvocationModel:
            """Return a description of a specific action.

            :param id: The action's ID (from the path).
            :param request: FastAPI dependency for the request object, used to
                find URLs via ``url_for``.
            :param _blob_manager: FastAPI dependency that enables `.Blob` objects
                to be serialised.

            :return: Details of the invocation.

            :raise HTTPException: with code ``404`` if the invocation is not
                found.
            """
            try:
                with self._invocations_lock:
                    return self._invocations[id].response(request=request)
            except KeyError as e:
                raise HTTPException(
                    status_code=404,
                    detail="No action invocation found with ID {id}",
                ) from e

        @app.get(
            ACTION_INVOCATIONS_PATH + "/{id}/output",
            response_model=Any,
            responses={
                200: {
                    "description": "Action invocation output",
                    "content": {
                        "*/*": {},
                    },
                },
                404: {"description": "Invocation ID not found"},
                503: {"description": "No result is available for this invocation"},
            },
        )
        def action_invocation_output(
            id: uuid.UUID, _blob_manager: BlobIOContextDep
        ) -> Any:
            """Get the output of an action invocation.

            This returns just the "output" component of the action invocation. If the
            output is a file, it will return the file.

            :param id: The action's ID (from the path).
            :param _blob_manager: FastAPI dependency that enables `.Blob` objects
                to be serialised.

            :return: The output of the invocation, as a `pydantic.BaseModel`
                instance. If this is a `.Blob`, it may be returned directly.

            :raise HTTPException: with code ``404`` if the invocation is not
                found.
            """
            with self._invocations_lock:
                try:
                    invocation: Any = self._invocations[id]
                except KeyError as e:
                    raise HTTPException(
                        status_code=404,
                        detail="No action invocation found with ID {id}",
                    ) from e
                if not invocation.output:
                    raise HTTPException(
                        status_code=503,
                        detail="No result is available for this invocation",
                    )
                if hasattr(invocation.output, "response") and callable(
                    invocation.output.response
                ):
                    # TODO: honour "accept" header
                    return invocation.output.response()
                return invocation.output

        @app.delete(
            ACTION_INVOCATIONS_PATH + "/{id}",
            response_model=None,
            responses={
                200: {
                    "description": "Cancel request sent",
                },
                404: {"description": "Invocation ID not found"},
                503: {"description": "Invocation may not be cancelled"},
            },
        )
        def delete_invocation(id: uuid.UUID) -> None:
            """Cancel an action invocation.

            :param id: The unique ID of the invocation to cancel (from the URL).

            :raise HTTPException: with code ``404`` if the invocation is not
                found, or ``503`` if the invocation is not currently running.
            """
            with self._invocations_lock:
                try:
                    invocation: Any = self._invocations[id]
                except KeyError as e:
                    raise HTTPException(
                        status_code=404,
                        detail="No action invocation found with ID {id}",
                    ) from e
                if invocation.status not in [
                    InvocationStatus.RUNNING,
                    InvocationStatus.PENDING,
                ]:
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            f"The invocation is {invocation.status} "
                            "and may not be cancelled."
                        ),
                    )
                invocation.cancel()
