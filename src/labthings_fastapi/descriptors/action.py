"""
Define an object to represent an Action, as a descriptor.
"""

from __future__ import annotations
from functools import partial
import inspect
from typing import TYPE_CHECKING, Annotated, Any, Callable, Optional, Literal, overload
from fastapi import Body, FastAPI, Request, BackgroundTasks
from pydantic import create_model
from ..actions import InvocationModel
from ..dependencies.invocation import CancelHook, InvocationID
from ..utilities.introspection import (
    EmptyInput,
    StrictEmptyInput,
    fastapi_dependency_params,
    get_docstring,
    get_summary,
    input_model_from_signature,
    return_type,
)
from ..outputs.blob import blob_to_model, get_model_media_type
from ..thing_description import type_to_dataschema
from ..thing_description.model import ActionAffordance, ActionOp, Form, Union

from weakref import WeakSet
from ..utilities import labthings_data, get_blocking_portal

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
    def __init__(
        self,
        func: Callable,
        response_timeout: float = 1,
        retention_time: float = 300,
    ):
        self.func = func
        self.response_timeout = response_timeout
        self.retention_time = retention_time
        self.dependency_params = fastapi_dependency_params(func)
        self.input_model = input_model_from_signature(
            func,
            remove_first_positional_arg=True,
            ignore=[p.name for p in self.dependency_params],
        )
        self.output_model = blob_to_model(return_type(func))
        self.invocation_model = create_model(
            f"{self.name}_invocation",
            __base__=InvocationModel,
            input=(self.input_model, ...),
            output=(Optional[self.output_model], None),
        )
        self.invocation_model.__name__ = f"{self.name}_invocation"

    @overload
    def __get__(self, obj: Literal[None], type=None) -> ActionDescriptor: ...

    @overload
    def __get__(self, obj: Thing, type=None) -> Callable: ...

    def __get__(
        self, obj: Optional[Thing], type=None
    ) -> Union[ActionDescriptor, Callable]:
        """The function, bound to an object as for a normal method.

        This currently doesn't validate the arguments, though it may do so
        in future. In its present form, this is equivalent to a regular
        Python method, i.e. all we do is supply the first argument, `self`.

        If `obj` is None, the descriptor is returned, so we can get
        the descriptor conveniently as an attribute of the class.
        """
        if obj is None:
            return self
        # TODO: do we attempt dependency injection here? I think not.
        # If we want dependency injection, we should be calling the action
        # via some sort of client object.
        return partial(self.func, obj)

    @property
    def name(self):
        """The name of the wrapped function"""
        return self.func.__name__

    @property
    def title(self):
        """A human-readable title"""
        return get_summary(self.func) or self.name

    @property
    def description(self):
        """A description of the action"""
        return get_docstring(self.func, remove_summary=True)

    def _observers_set(self, obj):
        """A set used to notify changes"""
        ld = labthings_data(obj)
        if self.name not in ld.action_observers:
            ld.action_observers[self.name] = WeakSet()
        return ld.action_observers[self.name]

    def emit_changed_event(self, obj, status):
        """Notify subscribers that the action status has changed

        NB this function **must** be run from a thread, not the event loop.
        """
        try:
            runner = get_blocking_portal(obj)
            if not runner:
                raise RuntimeError("Can't emit without a blocking portal")
            runner.start_task_soon(
                self.emit_changed_event_async,
                obj,
                status,
            )
        except Exception:
            # TODO: in the unit test, the get_blockint_port throws exception
            ...

    async def emit_changed_event_async(self, obj: Thing, value: Any):
        """Notify subscribers that the action status has changed"""
        action_name = self.name
        for observer in self._observers_set(obj):
            await observer.send(
                {
                    "messageType": "actionStatus",
                    "data": {"action name": action_name, "status": value},
                }
            )

    def add_to_fastapi(self, app: FastAPI, thing: Thing):
        """Add this action to a FastAPI app, bound to a particular Thing."""

        # We can't use the decorator in the usual way, because we'd need to
        # annotate the type of `body` with `self.model` which is only defined
        # at runtime.
        # The solution below is to manually add the annotation, before passing
        # the function to the decorator.
        def start_action(
            request: Request,
            body,
            id: InvocationID,
            cancel_hook: CancelHook,
            background_tasks: BackgroundTasks,
            **dependencies,
        ):
            try:
                action = thing.action_manager.invoke_action(
                    action=self,
                    thing=thing,
                    input=body,
                    dependencies=dependencies,
                    id=id,
                    cancel_hook=cancel_hook,
                )
                background_tasks.add_task(thing.action_manager.expire_invocations)
                return action.response(request=request)
            finally:
                try:
                    action._file_manager = request.state.file_manager
                except AttributeError:
                    pass  # This probably means there was no FileManager created.

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
        if get_model_media_type(self.output_model):
            responses[200]["content"][get_model_media_type(self.output_model)] = {}
        # Now we can add the endpoint to the app.
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
        def list_invocations():
            return thing.action_manager.list_invocations(self, thing, as_responses=True)

    def action_affordance(
        self, thing: Thing, path: Optional[str] = None
    ) -> ActionAffordance:
        """Represent the property in a Thing Description."""
        path = path or thing.path
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
