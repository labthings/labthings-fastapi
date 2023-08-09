"""
Define an object to represent an Action, as a descriptor.
"""
from __future__ import annotations
from functools import partial
from typing import TYPE_CHECKING, Annotated, Callable, Optional

from fastapi import Body, FastAPI

from ..actions import GenericInvocationModel
from ..utilities.introspection import (
    get_docstring,
    get_summary,
    input_model_from_signature,
    return_type,
)
from ..utilities.thing_description import type_to_dataschema
from ..utilities.w3c_td_model import ActionAffordance, ActionOp, Form

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


class ActionDescriptor():
    def __init__(
        self, 
        func: Callable,
        response_timeout: float = 1,
    ):
        self.func = func
        self.response_timeout = response_timeout
        self.input_model = input_model_from_signature(
            func, remove_first_positional_arg=True,
        )
        self.output_model = return_type(func)
        self.invocation_model = GenericInvocationModel[
            self.input_model, Optional[self.output_model]
        ]
        self.invocation_model.__name__ = f"{self.name}_invocation"

    def __get__(self, obj, type=None) -> Callable:
        """The function, bound to an object as for a normal method.
        
        This currently doesn't validate the arguments, though it may do so
        in future. In its present form, this is equivalent to a regular
        Python method, i.e. all we do is supply the first argument, `self`.

        If `obj` is None, the descriptor is returned, so we can get
        the descriptor conveniently as an attribute of the class.
        """
        if obj is None:
            return self
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
    
    def add_to_fastapi(self, app: FastAPI, thing: Thing):
        """Add this action to a FastAPI app, bound to a particular Thing."""
        # We can't use the decorator in the usual way, because we'd need to 
        # annotate the type of `body` with `self.model` which is only defined
        # at runtime.
        # The solution below is to manually add the annotation, before passing
        # the function to the decorator.
        def start_action(body): # We'll annotate body later
            return thing.action_manager.invoke_action(self, thing, body).response()
        start_action.__annotations__["body"] = Annotated[self.input_model, Body()]
        app.post(
            thing.path + self.name,
            response_model=GenericInvocationModel[self.input_model, type(None)],
            status_code=201,
            response_description="Action has been invoked (and may still be running).",
            description=f"## {self.title}\n\n {self.description} {ACTION_POST_NOTICE}",
            summary=self.title,
            responses={
                200: {
                    "description": "Action completed.",
                    "model": self.invocation_model,
                }
            }
        )(start_action)
        
        @app.get(
            thing.path + self.name,
            response_model=list[self.invocation_model],
            response_description=f"A list of every invocation of {self.name}.",
            description=(
                f"List all the invocations of {self.name}.\n {ACTION_GET_DESCRIPTION}"
            ),
            summary=f"All invocations of {self.name}."
        )
        def list_invocations():
            return thing.action_manager.list_invocations(self, thing, as_responses=True)

    def action_affordance(
            self, thing: Thing, path: Optional[str]=None
        ) -> ActionAffordance:
        """Represent the property in a Thing Description."""
        path = path or thing.path
        forms = [
            Form[ActionOp](
                href = path + self.name,
                op = [ActionOp.invokeaction]
            ),
        ]
        return ActionAffordance(
            title = self.title,
            forms = forms,
            description = self.description,
            input=type_to_dataschema(self.input_model, title=f"{self.name}_input"),
            output=type_to_dataschema(self.output_model, title=f"{self.name}_output"),
        )
