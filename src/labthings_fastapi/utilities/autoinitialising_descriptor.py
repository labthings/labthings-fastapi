from typing import overload, Literal, TypeVar, Generic, Optional, Union
from typing_extensions import Self
from abc import ABC, abstractmethod

PropertyType = TypeVar("PropertyType")
HostObjectType = TypeVar("HostObjectType")

class AutoinitialisingDescriptor(Generic[HostObjectType, PropertyType], ABC):
    """A descriptor that initialises an object when first accessed, once per instance
    
    This class simplifies writing code where a property should be initialised on first
    access - it's almost but not exactly like `functools.cached_property` in that:
    
    1. You can supply arguments
    2. The descriptor is returned when accessed via the class
    """
    def __init__(self, **kwargs):
        self._kwargs = kwargs

    def __set_name__(self, owner, name):
        self._name = name

    @property
    def name(self):
        """The name of the attribute to which this descriptor is assigned"""
        return self._name

    @overload
    def __get__(self, obj: Literal[None], type=None) -> Self:
        ...
    @overload
    def __get__(self, obj: HostObjectType, type=None) -> PropertyType:
        ...
    def __get__(
            self,
            obj: Optional[HostObjectType],
            type=None,
        ) -> Union[PropertyType, Self]:
        """The value of the property

        If `obj` is none (i.e. we are getting the attribute of the class), 
        we return the descriptor.

        Otherwise, we ensure the property is initialised on this object, and return
        it.
        """
        if obj is None:
            return self
        try:
            return obj.__dict__[self.name]
        except KeyError:
            obj.__dict__[self.name] = self.initial_value(obj)
            return obj.__dict__[self.name]
    
    @abstractmethod
    def initial_value(self, obj: HostObjectType) -> PropertyType:
        """Initialise the property."""
        raise NotImplementedError()
