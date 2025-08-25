"""Define an object to represent an Action, as a descriptor."""

from __future__ import annotations
from functools import partial
import inspect
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Callable,
    Optional,
    Literal,
    Union,
    overload,
)
from weakref import WeakSet

from fastapi import Body, FastAPI, Request, BackgroundTasks
from pydantic import create_model

from ..actions import InvocationModel
from ..dependencies.invocation import CancelHook, InvocationID
from ..dependencies.action_manager import ActionManagerContextDep
from ..utilities.introspection import (
    EmptyInput,
    StrictEmptyInput,
    fastapi_dependency_params,
    get_docstring,
    get_summary,
    input_model_from_signature,
    return_type,
)
from ..outputs.blob import BlobIOContextDep
from ..thing_description import type_to_dataschema
from ..thing_description._model import ActionAffordance, ActionOp, Form
from ..utilities import labthings_data, get_blocking_portal
from ..exceptions import NotConnectedToServerError

if TYPE_CHECKING:
    from ..thing import Thing


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


class ActionDescriptor:
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
        func: Callable,
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
        self.func = func
        self.response_timeout = response_timeout
        self.retention_time = retention_time
        self.dependency_params = fastapi_dependency_params(func)
        self.input_model = input_model_from_signature(
            func,
            remove_first_positional_arg=True,
            ignore=[p.name for p in self.dependency_params],
        )
        self.output_model = return_type(func)
        self.invocation_model = create_model(
            f"{self.name}_invocation",
            __base__=InvocationModel,
            input=(self.input_model, ...),
            output=(Optional[self.output_model], None),
        )
        self.invocation_model.__name__ = f"{self.name}_invocation"

    @overload
    def __get__(self, obj: Literal[None], type: type[Thing]) -> ActionDescriptor:  # noqa: D105
        ...

    @overload
    def __get__(self, obj: Thing, type: type[Thing] | None = None) -> Callable:  # noqa: D105
        ...

    def __get__(
        self, obj: Optional[Thing], type: Optional[type[Thing]] = None
    ) -> Union[ActionDescriptor, Callable]:
        """Return the function, bound to an object as for a normal method.

        This currently doesn't validate the arguments, though it may do so
        in future. In its present form, this is equivalent to a regular
        Python method, i.e. all we do is supply the first argument, `self`.

        If `obj` is None, the descriptor is returned, so we can get
        the descriptor conveniently as an attribute of the class.

        :param obj: the `.Thing` to which we are attached. This will be
            the first argument supplied to the function wrapped by this
            descriptor.
        :param type: the class of the `.Thing` to which we are attached.
            If the descriptor is accessed via the class it is returned
            directly.
        :return: the action function, bound to ``obj`` (when accessed
            via an instance), or the descriptor (accessed via the class).
        """
        if obj is None:
            return self
        # TODO: do we attempt dependency injection here? I think not.
        # If we want dependency injection, we should be calling the action
        # via some sort of client object.
        return partial(self.func, obj)

    @property
    def name(self) -> str:
        """The name of the wrapped function."""
        return self.func.__name__

    @property
    def title(self) -> str:
        """A human-readable title."""
        return get_summary(self.func) or self.name

    @property
    def description(self) -> str | None:
        """A description of the action."""
        return get_docstring(self.func, remove_summary=True)

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

        :raise NotConnectedToServerError: if the Thing calling the action is not
            connected to a server with a running event loop.
        """
        try:
            runner = get_blocking_portal(obj)
            if not runner:
                thing_name = obj.__class__.__name__
                msg = (
                    f"Cannot emit action changed event. Is {thing_name} connected to "
                    "a running server?"
                )
                raise NotConnectedToServerError(msg)
            runner.start_task_soon(
                self.emit_changed_event_async,
                obj,
                status,
            )
        except Exception:
            # TODO: in the unit test, the get_blocking_portal throws exception
            ...

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
        """

        # We can't use the decorator in the usual way, because we'd need to
        # annotate the type of `body` with `self.model` which is only defined
        # at runtime.
        # The solution below is to manually add the annotation, before passing
        # the function to the decorator.
        def start_action(
            action_manager: ActionManagerContextDep,
            _blob_manager: BlobIOContextDep,
            request: Request,
            body: Any,  # This annotation will be overwritten below.
            id: InvocationID,
            cancel_hook: CancelHook,
            background_tasks: BackgroundTasks,
            **dependencies: Any,
        ) -> InvocationModel:
            action = action_manager.invoke_action(
                action=self,
                thing=thing,
                input=body,
                dependencies=dependencies,
                id=id,
                cancel_hook=cancel_hook,
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
        assert thing.path is not None, "Can't add the endpoint without thing.path!"
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
        def list_invocations(
            action_manager: ActionManagerContextDep, _blob_manager: BlobIOContextDep
        ) -> list[InvocationModel]:
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
        """
        path = path or thing.path
        assert path is not None, "Can't generate forms without a path!"
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
