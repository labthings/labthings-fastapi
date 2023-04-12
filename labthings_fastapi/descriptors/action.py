from __future__ import annotations
"""
Define an object to represent an Action, as a descriptor.
"""
from typing import TYPE_CHECKING, Any
from fastapi import Body, FastAPI
from typing import Optional, Callable, Annotated
from ..utilities.introspection import input_model_from_signature
from ..actions import GenericInvocationModel
from functools import partial

if TYPE_CHECKING:
    from ..thing import Thing

class ActionDescriptor():
    def __init__(
        self, 
        func: Callable,
        response_timeout: float = 1,
    ):
        self.func = func
        self.response_timeout = response_timeout
        self.input_model = input_model_from_signature(
            func, remove_first_positional_arg=True
        )
        self.invocation_model = GenericInvocationModel[self.input_model, Any]
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
            response_model=self.invocation_model,
            status_code=201,
            response_description="Action invoked successfully"
        )(start_action)
        
        @app.get(
            thing.path + self.name,
            response_model=list[self.invocation_model],
        )
        def list_invocations():
            return thing.action_manager.list_invocations(self, thing, as_responses=True)

