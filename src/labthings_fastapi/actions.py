"""Actions module.

:ref:`actions` are represented by methods, decorated with the `.action`
decorator.

See the :ref:`actions` documentation for a top-level overview of actions in
LabThings-FastAPI.

Developer notes
---------------

Currently much of the code related to Actions is in `.action` and the
underlying `.ActionDescriptor`. This is likely to be refactored in the near
future.
"""

from __future__ import annotations
import datetime
import logging
from collections import deque
from functools import partial
import inspect
from threading import Thread, Lock
import uuid
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Callable,
    Concatenate,
    Generic,
    Optional,
    ParamSpec,
    TypeVar,
    overload,
)
from weakref import WeakSet
import weakref
from fastapi import FastAPI, HTTPException, Request, Body, BackgroundTasks
from pydantic import BaseModel, create_model

from .base_descriptor import BaseDescriptor
from .logs import add_thing_log_destination
from .utilities import model_to_dict, wrap_plain_types_in_rootmodel
from .invocations import InvocationModel, InvocationStatus, LogRecordModel
from .dependencies.invocation import NonWarningInvocationID
from .exceptions import (
    InvocationCancelledError,
    InvocationError,
    NoBlobManagerError,
    NotConnectedToServerError,
)
from .outputs.blob import BlobIOContextDep, blobdata_to_url_ctx
from . import invocation_contexts
from .utilities.introspection import (
    EmptyInput,
    StrictEmptyInput,
    fastapi_dependency_params,
    input_model_from_signature,
    return_type,
)
from .thing_description import type_to_dataschema
from .thing_description._model import ActionAffordance, ActionOp, Form, LinkElement
from .utilities import labthings_data


if TYPE_CHECKING:
    # We only need these imports for type hints, so this avoids circular imports.
    from .thing import Thing


__all__ = ["ACTION_INVOCATIONS_PATH", "Invocation", "ActionManager"]


ACTION_INVOCATIONS_PATH = "/action_invocations"
"""The API route used to list `.Invocation` objects."""


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
        """
        Thread.__init__(self, daemon=True)

        # keep track of the corresponding ActionDescriptor
        self.action_ref = weakref.ref(action)
        self.thing_ref = weakref.ref(thing)
        self.input = input if input is not None else EmptyInput()
        self.dependencies = dependencies if dependencies is not None else {}

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
        """The `.ActionDescriptor` object running in this thread.

        :raises RuntimeError: if the action descriptor has been deleted.
            This should never happen, as the descriptor is a property of
            a class, which won't be deleted.
        """
        action = self.action_ref()
        if action is None:  # pragma: no cover
            # Action descriptors should only be deleted after the server has
            # stopped, so this error should never occur.
            raise RuntimeError("The action for an `Invocation` has been deleted!")
        return action

    @property
    def thing(self) -> Thing:
        """The `.Thing` to which the action is bound, i.e. this is ``self``.

        :raises RuntimeError: if the Thing no longer exists.
        """
        thing = self.thing_ref()
        if thing is None:  # pragma: no cover
            # this error block is primarily for mypy: the Thing will exist as
            # long as the server is running, so we should never hit this error.
            raise RuntimeError("The `Thing` on which an action was run is missing!")
        return thing

    @property
    def cancel_hook(self) -> invocation_contexts.CancelEvent:
        """The cancel event associated with this Invocation."""
        return invocation_contexts.get_cancel_event(self.id)

    def cancel(self) -> None:
        """Cancel the task by requesting the code to stop.

        This is an opt-in feature: the action must use
        a `.CancelHook` dependency and periodically check it.
        """
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

        :raises RuntimeError: if there is no Thing associated with the invocation.
        """
        # self.action evaluates to an ActionDescriptor. This confuses mypy,
        # which thinks we are calling ActionDescriptor.__get__.
        action: ActionDescriptor = self.action  # type: ignore[call-overload]
        logger = self.thing.logger
        # The line below saves records matching our ID to ``self._log``
        add_thing_log_destination(self.id, self._log)
        with invocation_contexts.set_invocation_id(self.id):
            try:
                action.emit_changed_event(self.thing, self._status.value)

                thing = self.thing
                kwargs = model_to_dict(self.input)
                if thing is None:  # pragma: no cover
                    # The Thing is stored as a weakref, but it will always exist
                    # while the server is running - this error should never
                    # occur.
                    raise RuntimeError("Cannot start an invocation without a Thing.")

                with self._status_lock:
                    self._status = InvocationStatus.RUNNING
                    self._start_time = datetime.datetime.now()
                    action.emit_changed_event(self.thing, self._status.value)

                bound_method = action.__get__(thing)
                # Actually run the action
                ret = bound_method(**kwargs, **self.dependencies)

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

        :return: an `.Invocation` object that has been started.
        """
        thread = Invocation(
            action=action,
            thing=thing,
            input=input,
            dependencies=dependencies,
            id=id,
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


ACTION_POST_NOTICE = """
## Important note

This `POST` request starts an Action, i.e. the server will do something
that may continue after the HTTP request has been responded to.  The
response will always be an ActionInvocation object, that details the current
status of the action and provides an interface to poll for completion.

If the action completes within a specified timeout, we will return
an HTTP status code of `200` and the return value will include any
output from the action.  If it does not complete, we will return a
`201` response code, and the action's endpoint may be polled to follow
its progress.
"""

ACTION_GET_DESCRIPTION = """
This will include times and input values, as well as output values for
actions that have completed. These actions will also show up under the
`action_invocations` endpoint, and can also be retrieved individually
using the link included in each action.
"""


ActionParams = ParamSpec("ActionParams")
ActionReturn = TypeVar("ActionReturn")
OwnerT = TypeVar("OwnerT", bound="Thing")


class ActionDescriptor(
    BaseDescriptor[Callable[ActionParams, ActionReturn]],
    Generic[ActionParams, ActionReturn, OwnerT],
):
    """Wrap actions to enable them to be run over HTTP.

    This class is responsible for generating the action description for
    the :ref:`wot_td` and creating the function that responds to ``POST``
    requests to invoke the action.

    .. note::
        Descriptors are instantiated once per class. This means that we cannot
        assume there is only one action corresponding to this descriptor: there
        may be multiple `.Thing` instances with the same descriptor. That is
        why the host `.Thing` must be passed to many functions as an argument,
        and why observers, for example, must be keyed by the `.Thing` rather
        than kept as a property of ``self``.
    """

    def __init__(
        self,
        func: Callable[Concatenate[OwnerT, ActionParams], ActionReturn],
        response_timeout: float = 1,
        retention_time: float = 300,
    ) -> None:
        """Create a new action descriptor.

        The action descriptor wraps a method of a `.Thing`. It may still be
        called from Python in the same way, but it will also be added to the
        HTTP API and automatic documentation.

        :param func: is the method that will be run when the action is called.
        :param response_timeout: is how long we should wait before returning a
            response to the client. This is not currently used, as we always
            return immediately with a `201` code. In the future, it may set a
            default time to wait before responding. If the action finishes
            before we respond, we will be able to return the completed action
            and its output. If the action is still running, we return a 201
            code and data enabling the client to poll to find out the status
            of the action.
        :param retention_time: how long, in seconds, the action should be kept
            for after it has completed.
        """
        super().__init__()
        self.func = func
        if func.__doc__ is not None:
            # Use the docstring from the function, if there is one.
            self.__doc__ = func.__doc__
        name = func.__name__  # this is checked in __set_name__
        self.response_timeout = response_timeout
        self.retention_time = retention_time
        self.dependency_params = fastapi_dependency_params(func)
        self.input_model = input_model_from_signature(
            func,
            remove_first_positional_arg=True,
            ignore=[p.name for p in self.dependency_params],
        )
        self.output_model = wrap_plain_types_in_rootmodel(return_type(func))
        self.invocation_model = create_model(
            f"{name}_invocation",
            __base__=InvocationModel,
            input=(self.input_model, ...),
            output=(Optional[self.output_model], None),
        )
        self.invocation_model.__name__ = f"{name}_invocation"

    def __set_name__(self, owner: type[Thing], name: str) -> None:
        """Ensure the action name matches the function name.

        It's assumed in a few places that the function name and the
        descriptor's name are the same. This should always be the case
        if it's used as a decorator.

        :param owner: The class owning the descriptor.
        :param name: The name of the descriptor in the class.
        :raises ValueError: if the action name does not match the function name.
        """
        super().__set_name__(owner, name)
        if self.name != self.func.__name__:
            raise ValueError(
                f"Action name '{self.name}' does not match function name "
                f"'{self.func.__name__}'",
            )

    def instance_get(self, obj: Thing) -> Callable[ActionParams, ActionReturn]:
        """Return the function, bound to an object as for a normal method.

        This currently doesn't validate the arguments, though it may do so
        in future. In its present form, this is equivalent to a regular
        Python method, i.e. all we do is supply the first argument, `self`.

        :param obj: the `.Thing` to which we are attached. This will be
            the first argument supplied to the function wrapped by this
            descriptor.
        :return: the action function, bound to ``obj``.
        """
        # `obj` should be of type `OwnerT`, but `BaseDescriptor` currently
        # isn't generic in the type of the owning Thing, so we can't express
        # that here.
        return partial(self.func, obj)  # type: ignore[arg-type]

    def _observers_set(self, obj: Thing) -> WeakSet:
        """Return a set used to notify changes.

        Note that we need to supply the `.Thing` we are looking at, as in
        general there may be more than one object of the same type, and
        descriptor instances are shared between all instances of their class.

        :param obj: The `.Thing` on which the action is being observed.

        :return: a weak set of callables to notify on changes to the action.
            This is used by websocket endpoints.
        """
        ld = labthings_data(obj)
        if self.name not in ld.action_observers:
            ld.action_observers[self.name] = WeakSet()
        return ld.action_observers[self.name]

    def emit_changed_event(self, obj: Thing, status: str) -> None:
        """Notify subscribers that the action status has changed.

        This function is run from within the `.Invocation` thread that
        is created when an action is called. It must be run from a thread
        as it is communicating with the event loop via an `asyncio` blocking
        portal. Async code must not use the blocking portal as it can deadlock
        the event loop.

        :param obj: The `.Thing` on which the action is being observed.
        :param status: The status of the action, to be sent to observers.
        """
        obj._thing_server_interface.start_async_task_soon(
            self.emit_changed_event_async,
            obj,
            status,
        )

    async def emit_changed_event_async(self, obj: Thing, value: Any) -> None:
        """Notify subscribers that the action status has changed.

        This is an async function that must be run in the `anyio` event loop.
        It will send messages to each observer to notify them that something
        has changed.

        :param obj: The `.Thing` on which the action is defined.
            `.ActionDescriptor` objects are unique to the class, but there may
            be more than one `.Thing` attached to a server with the same class.
            We use ``obj`` to look up the observers of the current `.Thing`.
        :param value: The action status to communicate to the observers.
        """
        action_name = self.name
        for observer in self._observers_set(obj):
            await observer.send(
                {
                    "messageType": "actionStatus",
                    "data": {"action name": action_name, "status": value},
                }
            )

    def add_to_fastapi(self, app: FastAPI, thing: Thing) -> None:
        """Add this action to a FastAPI app, bound to a particular Thing.

        This function creates two functions to handle ``GET`` and ``POST``
        requests to the action's endpoint, and adds them to the `fastapi.FastAPI`
        application.

        :param app: The `fastapi.FastAPI` app to add the endpoint to.
        :param thing: The `.Thing` to which the action is attached. Bear in
            mind that the descriptor may be used by more than one `.Thing`,
            so this can't be a property of the descriptor.

        :raises NotConnectedToServerError: if the function is run before the
            ``thing`` has a ``path`` property. This is assigned when the `.Thing`
            is added to a server.
        """

        # We can't use the decorator in the usual way, because we'd need to
        # annotate the type of `body` with `self.model` which is only defined
        # at runtime.
        # The solution below is to manually add the annotation, before passing
        # the function to the decorator.
        def start_action(
            _blob_manager: BlobIOContextDep,
            request: Request,
            body: Any,  # This annotation will be overwritten below.
            id: NonWarningInvocationID,
            background_tasks: BackgroundTasks,
            **dependencies: Any,
        ) -> InvocationModel:
            action_manager = thing._thing_server_interface._action_manager
            action = action_manager.invoke_action(
                action=self,
                thing=thing,
                input=body,
                dependencies=dependencies,
                id=id,
            )
            background_tasks.add_task(action_manager.expire_invocations)
            return action.response(request=request)

        if issubclass(self.input_model, EmptyInput):
            annotation = Body(default_factory=StrictEmptyInput)
        else:
            annotation = Body()
        start_action.__annotations__["body"] = Annotated[self.input_model, annotation]
        # The block below passes through parameters of the action function that are
        # FastAPI dependencies, so they can be properly injected.
        # It also removes the `**dependencies` parameter from the signature.
        # This means that `dependencies` is a dict mapping parameter names to
        # **resolved** dependency objects.
        sig = inspect.signature(start_action)
        params = [p for p in sig.parameters.values() if p.name != "dependencies"]
        params += self.dependency_params
        start_action.__signature__ = sig.replace(  # type: ignore[attr-defined]
            parameters=params
        )
        # We construct a responses dictionary that allows us to specify the model or
        # the media type of the returned file. Not yet actually used.
        responses: dict[int | str, dict[str, Any]] = {
            200: {  # TODO: This does not currently get used
                "description": "Action completed.",
                "content": {
                    "application/json": {},
                },
            },
        }
        try:
            responses[200]["model"] = self.output_model
            pass
        except AttributeError:
            print(f"Failed to generate response model for action {self.name}")
        # Add an additional media type if we may return a file
        if hasattr(self.output_model, "media_type"):
            responses[200]["content"][self.output_model.media_type] = {}
        # Now we can add the endpoint to the app.
        if thing.path is None:
            raise NotConnectedToServerError(
                "Can't add the endpoint without thing.path!"
            )
        app.post(
            thing.path + self.name,
            response_model=self.invocation_model,
            status_code=201,
            response_description="Action has been invoked (and may still be running).",
            description=f"## {self.title}\n\n {self.description} {ACTION_POST_NOTICE}",
            summary=self.title,
            responses=responses,
        )(start_action)

        @app.get(
            thing.path + self.name,
            response_model=list[self.invocation_model],  # type: ignore
            # MyPy doesn't like the line above - but it works for FastAPI
            # to generate a response model.
            response_description=f"A list of every invocation of {self.name}.",
            description=(
                f"List all the invocations of {self.name}.\n {ACTION_GET_DESCRIPTION}"
            ),
            summary=f"All invocations of {self.name}.",
        )
        def list_invocations(_blob_manager: BlobIOContextDep) -> list[InvocationModel]:
            action_manager = thing._thing_server_interface._action_manager
            return action_manager.list_invocations(self, thing)

    def action_affordance(
        self, thing: Thing, path: Optional[str] = None
    ) -> ActionAffordance:
        """Represent the property in a Thing Description.

        This function describes the Action in :ref:`wot_td` format.

        :param thing: The `.Thing` to which the action is attached.
        :param path: The prefix applied to all endpoints associated with the
            `.Thing`. This is the URL for the Thing Description. If it is
            omitted, we use the ``path`` property of the ``thing``.

        :return: An `.ActionAffordance` describing this action.

        :raises NotConnectedToServerError: if the function is run before the
            ``thing`` has a ``path`` property. This is assigned when the `.Thing`
            is added to a server.
        """
        path = path or thing.path
        if path is None:
            raise NotConnectedToServerError("Can't generate forms without a path!")
        forms = [
            Form[ActionOp](href=path + self.name, op=[ActionOp.invokeaction]),
        ]
        return ActionAffordance(
            title=self.title,
            forms=forms,
            description=self.description,
            input=type_to_dataschema(self.input_model, title=f"{self.name}_input"),
            output=type_to_dataschema(self.output_model, title=f"{self.name}_output"),
        )


@overload
def action(
    func: Callable[Concatenate[OwnerT, ActionParams], ActionReturn], **kwargs: Any
) -> ActionDescriptor[ActionParams, ActionReturn, OwnerT]: ...


@overload
def action(
    **kwargs: Any,
) -> Callable[
    [
        Callable[Concatenate[OwnerT, ActionParams], ActionReturn],
    ],
    ActionDescriptor[ActionParams, ActionReturn, OwnerT],
]: ...


def action(
    func: Callable[Concatenate[OwnerT, ActionParams], ActionReturn] | None = None,
    **kwargs: Any,
) -> (
    ActionDescriptor[ActionParams, ActionReturn, OwnerT]
    | Callable[
        [
            Callable[Concatenate[OwnerT, ActionParams], ActionReturn],
        ],
        ActionDescriptor[ActionParams, ActionReturn, OwnerT],
    ]
):
    r"""Mark a method of a `.Thing` as a LabThings Action.

    Methods decorated with :deco:`action` will be available to call
    over HTTP as actions. See :ref:`actions` for an introduction to the concept
    of actions.

    This decorator may be used with or without arguments.

    :param func: The method to be decorated as an action.
    :param \**kwargs: Keyword arguments are passed to the constructor
        of `.ActionDescriptor`.

    :return: Whether used with or without arguments, the result is that
        the method is wrapped in an `.ActionDescriptor`, so it can be
        called as usual, but will also be exposed over HTTP.
    """
    # This can be used with or without arguments.
    # If we're being used without arguments, we will
    # have a non-None value for `func` and defaults
    # for the arguments.
    # If the decorator does have arguments, we must
    # return a partial object, which then calls the
    # wrapped function once.
    if func is not None:
        return ActionDescriptor(func, **kwargs)
    else:
        return partial(ActionDescriptor, **kwargs)
