from __future__ import annotations
"""
Define an object to represent an Action, as a descriptor.
"""
from typing import TYPE_CHECKING, Any, Optional
from fastapi import Body, FastAPI
from typing import Annotated
from ..thing_description import PropertyAffordance, Form

if TYPE_CHECKING:
    from ..thing import Thing

class PropertyDescriptor():
    """A property that can be accessed via the HTTP API
    
    By default, a PropertyDescriptor is "dumb", i.e. it acts just like
    a normal variable.
    """
    model: type
    readonly: bool = False
    def __init__(
            self, 
            model: type, 
            initial_value: Any = None,
            readonly: bool = False,
            description: Optional[str] = None,
            title: Optional[str] = None,
        ):
        self.model = model
        self.readonly = readonly
        self.initial_value = initial_value
        self.description = description
        self.title = title
        if self.description and not self.title:
            self.title = self.description.partition("\n")[0]

    def __set_name__(self, owner, name: str):
        self._name = name
        if not self.title:
            self.title = name

    def __get__(self, obj, type=None) -> Any:
        """The value of the property

        If `obj` is none (i.e. we are getting the attribute of the class), 
        we return the descriptor.
        """
        if obj is None:
            return self
        return obj.__dict__.get(self.name, self.initial_value)
    
    def __set__(self, obj, value):
        """Set the property's value"""
        obj.__dict__[self.name] = value
    
    @property
    def name(self):
        """The name of the property"""
        return self._name
    
    def add_to_fastapi(self, app: FastAPI, thing: Thing):
        """Add this action to a FastAPI app, bound to a particular Thing."""
        # We can't use the decorator in the usual way, because we'd need to 
        # annotate the type of `body` with `self.model` which is only defined
        # at runtime.
        # The solution below is to manually add the annotation, before passing
        # the function to the decorator.
        if not self.readonly:
            def set_property(body): # We'll annotate body later
                return self.__set__(thing, body)
            set_property.__annotations__["body"] = Annotated[self.model, Body()]
            app.post(
                thing.path + self.name,
                status_code=201,
                response_description="Property set successfully",
                summary=f"Set {self.name}",
                description=f"Set {self.name}"
            )(set_property)
        
        @app.get(
            thing.path + self.name,
            response_model=self.model,
            response_description=f"Value of {self.name}"
        )
        def get_property():
            return self.__get__(thing)

    def property_affordance(self, thing: Thing, path: Optional[str]=None) -> PropertyAffordance:
        path = path or thing.path
        ops = ["readproperty"]
        if not self.readonly:
            ops.append("writeproperty")
        forms = [
            Form(
                href = path + self.name,
                op = ops
            ),
        ]

        return PropertyAffordance(
            title = self.title,
            forms = forms,
            readonly = self.readonly,
            description = self.description,

        )