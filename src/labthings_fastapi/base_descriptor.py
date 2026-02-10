r"""A base class for descriptors in LabThings.

:ref:`descriptors` are used to describe :ref:`wot_affordances` in LabThings-FastAPI.
There is some behaviour common to most of these, and `.BaseDescriptor` centralises
the code that implements it.

`.BaseDescriptor` provides consistent handling of name, title, and description, as
well as implementing the convention that descriptors return themselves when accessed
as class attributes. It also provides `.BaseDescriptor.descriptor_info` to return
an object that may be used to refer to the descriptor (see later).

`.FieldTypedBaseDescriptor` is a subclass of `.BaseDescriptor` that adds "field typing",
i.e. the ability to determine the type of the descriptor's value from a type annotation
on the class attribute. This is particularly important for :ref:`properties`\ .

`.BaseDescriptorInfo` is a class that describes a descriptor, optionally bound to an
instance. This allows us to pass around references to descriptors without confusing
type checkers, and without needing to separately pass the instance along with the
descriptor.

`.DescriptorInfoCollection` is a mapping of descriptor names to `.BaseDescriptorInfo`
objects, and may be used to retrieve all descriptors of a particular type on a
`.Thing`\ .
"""

from __future__ import annotations
import ast
import builtins
from collections.abc import Iterator
import inspect
from itertools import pairwise
import textwrap
from typing import Any, overload, Generic, Mapping, TypeVar, TYPE_CHECKING
from types import MappingProxyType
import typing
from weakref import WeakKeyDictionary, ref
from typing_extensions import Self

from .utilities.introspection import get_docstring, get_summary
from .exceptions import MissingTypeError, InconsistentTypeError, NotBoundToInstanceError

if TYPE_CHECKING:
    from .thing import Thing

Value = TypeVar("Value")
"""The value returned by the descriptor, when called on an instance."""

Owner = TypeVar("Owner", bound="Thing")
"""A Thing subclass that owns a descriptor."""

Descriptor = TypeVar("Descriptor", bound="BaseDescriptor")
"""The type of a descriptor that's referred to by a `BaseDescriptorInfo` object."""

FTDescriptorT = TypeVar("FTDescriptorT", bound="FieldTypedBaseDescriptor")
"""The type of a field typed descriptor."""

DescriptorInfoT = TypeVar("DescriptorInfoT", bound="BaseDescriptorInfo")
"""The type of `.BaseDescriptorInfo` returned by a descriptor"""

OptionallyBoundInfoT = TypeVar("OptionallyBoundInfoT", bound="OptionallyBoundInfo")
"""The type of `OptionallyBoundInfo` returned by a descriptor."""


class DescriptorNotAddedToClassError(RuntimeError):
    """Descriptor has not yet been added to a class.

    This error is raised if certain properties of descriptors are accessed
    before ``__set_name__`` has been called on the descriptor.  ``__set_name__``
    is part of the descriptor protocol, and is called when a class is defined
    to notify the descriptor of its name and owning class.

    If you see this error, it often means that a descriptor has been instantiated
    but not attached to a class, for example:

    .. code-block:: python

        import labthings as lt


        class Test(lt.Thing):
            myprop: int = lt.property(default=0)  # This is OK


        orphaned_prop: int = lt.property(default=0)  # Not OK

        Test.myprop.model  # Evaluates to a pydantic model

        orphaned_prop.model  # Raises this exception
    """


class DescriptorAddedToClassTwiceError(RuntimeError):
    """A Descriptor has been added to a class more than once.

    This error is raised if ``__set_name__`` is called more than once on a
    descriptor. This happens when either the same descriptor instance is
    used twice in one class definition, or if a descriptor instance is used
    on more than one class.

    .. note::

        `.FunctionalProperty` includes a special case that will ignore the
        ``__set_name__`` call corresponding to the setter. This allows the
        property to be defined like ``prop4`` below, even though it does
        assign the descriptor to two names. That behaviour is specific to
        `.FunctionalProperty` and `.FunctionalSetting` and is not part of
        `.BaseDescriptor` because `.BaseDescriptor` has no setter.

        ``mypy`` does not allow custom property-like descriptors to follow the
        syntax used by the built-in ``property`` of giving both the getter and
        setter functions the same name: this causes an error because it is
        a redefinition. We suggest using a different name for the setter to
        work around this, hence the need for an exception.

    .. code-block:: python

        class MyDescriptor(BaseDescriptor):
            "An example descriptor that inherits from BaseDescriptor."

            def __init__(getter=None):
                "Initialise the descriptor, allowing use as a decorator."
                self._getter = getter

            def setter(self, setter):
                "Add a setter to the descriptor."
                self._setter = setter
                return self


        class Example:
            "An example class with descriptors."

            # prop1 is fine - only used once.
            prop1 = MyDescriptor()

            # prop2 reuses the name ``prop2`` which may confuse ``mypy`` but
            # will only call ``__set_name__`` once.
            @MyDescriptor
            def prop2(self):
                "A dummy property"
                return False

            @prop2.setter
            def prop2(self, val):
                "Set the dummy property"
                pass

            # prop3a and prop3b will cause this error
            prop3a = MyDescriptor()
            prop3b = MyDescriptor()

            # prop4 and set_prop4 will cause this error on BaseDescriptor
            # but there is a specific exception in FunctionalProperty
            # to allow this form.
            @MyDescriptor
            def prop4(self):
                "An example property with two names"
                return True

            @prop4.setter
            def _set_prop4(self, val):
                "A setter for prop4 that is not named prop4."
                pass

    .. note::

        Because this exception is raised in ``__set_name__`` it will not
        appear to come from the descriptor assignment, but instead it will
        be raised at the end of the class definition. The descriptor name(s)
        should be in the error message.

    """


class OptionallyBoundInfo(Generic[Owner]):
    """A class that may be bound to an owning object or to a class."""

    def __init__(self, obj: Owner | None, cls: type[Owner] | None = None) -> None:
        r"""Initialise an `OptionallyBoundInfo` object.

        This initialises the object, optionally binding it to `obj` if it is
        not `None`\ .

        :param obj: The object to which this info object is bound. If
            it is `None` (default), the object will be unbound and will refer to
            the descriptor as attached to the class. This may mean that some
            methods are unavailable.

        :param cls: The class to which this info object refers. May be omitted
            if `obj` is supplied.

        :raises ValueError: if neither `obj` nor `cls` is supplied.
        :raises TypeError: if `obj` and `cls` are both supplied, but `obj` is not
            an instance of `cls`. Note that `cls` does not have to be equal to
            ``obj.__class__``\ , it just has to pass `isinstance`\ .
        """
        if cls is None:
            if obj is None:
                raise ValueError("Either `obj` or `cls` must be supplied.")
            cls = obj.__class__
        if obj and not isinstance(obj, cls):
            raise TypeError(f"{obj} is not an instance of {cls}.")
        self._descriptor_cls = cls
        self._bound_to_obj = obj

    @property
    def owning_class(self) -> type[Owner]:
        """Retrieve the class this info object is describing."""
        return self._descriptor_cls

    @property
    def owning_object(self) -> Owner | None:
        """Retrieve the object to which this info object is bound, if present."""
        return self._bound_to_obj

    @property
    def is_bound(self) -> bool:
        """Whether this info object is bound to an instance.

        If this property is `False` then this object refers only to a class. If it
        is `True` then we are describing a particular instance.
        """
        return self._bound_to_obj is not None

    def owning_object_or_error(self) -> Owner:
        """Return the `.Thing` instance to which we are bound, or raise an error.

        This is mostly a convenience function that saves type-checking boilerplate.

        :return: the owning object.
        :raises NotBoundToInstanceError: if this object is not bound.
        """
        obj = self._bound_to_obj
        if obj is None:
            raise NotBoundToInstanceError("Can't return the object, as we are unbound.")
        return obj


class BaseDescriptorInfo(
    OptionallyBoundInfo[Owner],
    Generic[Descriptor, Owner, Value],
):
    r"""A class that describes a `BaseDescriptor`\ .

    This class is used internally by LabThings to describe :ref:`properties`\ ,
    :ref:`actions`\ , and other attributes of a `.Thing`\ . It's not usually
    encountered directly by someone using LabThings, except as a base class for
    `.Action`\ , `.Property` and others.

    LabThings uses descriptors to represent the :ref:`affordances` of a `.Thing`\ .
    However, passing descriptors around isn't very elegant for two reasons:

    * Holding references to Descriptor objects can confuse static type checkers.
    * Descriptors are attached to a *class* but do not know which *object* they
        are defined on.

    This class allows the attributes of a descriptor to be accessed, and holds
    a reference to the underlying descriptor and its owning class. It may
    optionally hold a reference to a `.Thing` instance, in which case it is
    said to be "bound". This means there's no need to separately pass the `.Thing`
    along with the descriptor, which should help keep things simple in several
    places in the code.
    """

    def __init__(
        self, descriptor: Descriptor, obj: Owner | None, cls: type[Owner] | None = None
    ) -> None:
        r"""Initialise an `OptionallyBoundInfo` object.

        This sets up a BaseDescriptorInfo object, describing ``descriptor`` and
        optionally bound to ``obj``\ .

        :param descriptor: The descriptor that this object will describe.
        :param obj: The object to which this `.BaseDescriptorInfo` is bound. If
            it is `None` (default), the object will be unbound and will refer to
            the descriptor as attached to the class. This may mean that some
            methods are unavailable.
        :param cls: The class to which we are bound. Only required if ``obj`` is
            `None`\ .

        :raises ValueError: if both ``obj`` and ``cls`` are `None`\ .
        """
        super().__init__(obj, cls)
        self._descriptor_ref = ref(descriptor)
        if cls is None:
            if obj is None:
                raise ValueError("Either `obj` or `cls` must be supplied.")
            cls = obj.__class__
        self._descriptor_cls = cls
        self._bound_to_obj = obj

    def get_descriptor(self) -> Descriptor:
        """Retrieve the descriptor object.

        :return: The descriptor object
        :raises RuntimeError: if the descriptor was garbage collected. This should
            never happen.
        """
        descriptor = self._descriptor_ref()
        if descriptor is None:
            msg = "A descriptor was deleted too early. This may be a LabThings Bug."
            raise RuntimeError(msg)
        return descriptor

    @property
    def name(self) -> str:
        """The name of the descriptor.

        This should be the same as the name of the attribute in Python.
        """
        return self.get_descriptor().name

    @property
    def title(self) -> str:
        """The title of the descriptor."""
        return self.get_descriptor().title

    @property
    def description(self) -> str | None:
        """A description (usually the docstring) of the descriptor."""
        return self.get_descriptor().description

    def get(self) -> Value:
        """Get the value of the descriptor.

        This method only works on a bound info object, it will raise an error
        if called via a class rather than a `.Thing` instance.

        :return: the value of the descriptor.
        :raises NotBoundToInstanceError: if called on an unbound object.
        """
        if not self.is_bound:
            msg = f"We can't get the value of {self.name} when called on a class."
            raise NotBoundToInstanceError(msg)
        descriptor = self.get_descriptor()
        return descriptor.__get__(self.owning_object_or_error())

    def set(self, value: Value) -> None:
        """Set the value of the descriptor.

        This method may only be called if the DescriptorInfo object is bound to a
        `.Thing` instance. It will raise an error if called on a class.

        :param value: the new value.

        :raises NotBoundToInstanceError: if called on an unbound info object.
        """
        if not self.is_bound:
            msg = f"We can't set the value of {self.name} when called on a class."
            raise NotBoundToInstanceError(msg)
        descriptor = self.get_descriptor()
        descriptor.__set__(self.owning_object_or_error(), value)

    def __eq__(self, other: Any) -> bool:
        """Determine if this object is equal to another one.

        :param other: the object we're comparing to.
        :return: whether the two objects are equal.
        """
        return (
            self.__class__ == other.__class__
            and self.name == other.name
            and self.owning_class == other.owning_class
            and self.owning_object == other.owning_object
        )

    def __repr__(self) -> str:
        """Represent the DescriptorInfo object as a string.

        :return: a string representing the info object.
        """
        descriptor = f"{self.owning_class.__name__}.{self.name}"
        bound = f" bound to {self.owning_object}>" if self.is_bound else ""
        return f"<{self.__class__.__name__} for {descriptor}{bound}>"


class BaseDescriptor(Generic[Owner, Value]):
    r"""A base class for descriptors in LabThings-FastAPI.

    This class implements several behaviours common to descriptors in LabThings:

    * The descriptor remembers the name it's assigned to in ``name``, for use in
        :ref:`gen_docs`\ .
    * The descriptor inspects its owning class, and looks for an attribute
        docstring (i.e. a string constant immediately following the attribute
        assignment).
    * When called as a class attribute, the descriptor returns itself, as done by
        e.g. `property`.
    * The docstring and name are used to provide a ``title`` and ``description``
        that may be used in :ref:`gen_docs` and elsewhere.

    .. code-block:: python

        class Example:
            my_prop = BaseDescriptor()
            '''My Property.

            This is a nice long docstring describing my property, which
            can span multiple lines.
            '''


        p = Example.my_prop
        assert p.name == "my_prop"
        assert p.title == "My Property."
        assert p.description.startswith("This is")
    """

    def __init__(self) -> None:
        """Initialise a BaseDescriptor."""
        super().__init__()
        self._name: str | None = None
        self._title: str | None = None
        self._description: str | None = None
        # We set the instance __doc__ to None so the descriptor class docstring
        # doesn't get picked up by OpenAPI/Thing Description.
        self.__doc__ = None
        # We explicitly check when __set_name__ is called, so we can raise helpful
        # errors
        self._set_name_called: bool = False
        self._owner_name: str = ""

    def __set_name__(self, owner: type[Owner], name: str) -> None:
        r"""Take note of the name to which the descriptor is assigned.

        This is called when the descriptor is assigned to an attribute of a class.
        This function remembers the name, so it can be used in :ref:`gen_docs`\ .

        This function also inspects the owning class, and will retrieve the
        docstring for its attribute. This allows us to use a string immediately
        after the descriptor is defined, rather than passing the docstring as
        an argument.
        See `.get_class_attribute_docstrings` for more details.

        :param owner: the `.Thing` subclass to which we are being attached.
        :param name: the name to which we have been assigned.

        :raises DescriptorAddedToClassTwiceError: if the descriptor has been
            assigned to two class attributes.
        """
        if self._set_name_called:
            raise DescriptorAddedToClassTwiceError(
                f"The descriptor {self._name} on {self._owner_name} has been "
                f"added to a class a second time ({owner.__qualname__}.{name}). "
                "This descriptor may only be added to a class once."
            )
        # Remember the name to which we're assigned. Accessed by the read only
        # property ``name``.
        self._set_name_called = True
        self._name = name
        self._owner_name = owner.__qualname__
        self._owner_ref = ref(owner)

        # Check for docstrings on the owning class, and retrieve the one for
        # this attribute (identified by `name`).
        attr_docs = get_class_attribute_docstrings(owner)
        if name in attr_docs:
            self.__doc__ = attr_docs[name]

    def assert_set_name_called(self) -> None:
        """Raise an exception if ``__set_name__`` has not yet been called.

        :raises DescriptorNotAddedToClassError: if ``__set_name__`` has not yet
            been called.
        """
        if not self._set_name_called:
            raise DescriptorNotAddedToClassError(
                f"{self.__class__.__name__} must be assigned to an attribute of "
                "a class, as part of the class definition. This exception is "
                "raised because `__set_name__` has not yet been called, which "
                "usually means it was not instantiated as a class attribute."
            )

    @property
    def name(self) -> str:
        """The name of this descriptor.

        When the descriptor is assigned to an attribute of a class, we
        remember the name of the attribute. There will be some time in
        between the descriptor being instantiated and the name being set.

        We call `.BaseDescriptor.assert_set_name_called` so an exception will
        be raised if this property is accessed before the descriptor has been
        assigned to a class attribute.

        The ``name`` of :ref:`wot_affordances` is used in their URL and in
        the :ref:`gen_docs` served by LabThings.

        :raises DescriptorNotAddedToClassError: if ``__set_name__`` has not yet
            been called.
        """
        self.assert_set_name_called()
        if self._name is None:  # pragma: no cover
            raise DescriptorNotAddedToClassError("`_name` is not set.")
        # The exception is mostly for typing: if `assert_set_name_called``
        # doesn't raise an error, `BaseDescriptor.__set_name__` has been
        # called and thus `self._name`` has been set.
        return self._name

    @property
    def title(self) -> str:
        """A human-readable title for the descriptor.

        The :ref:`wot_td` requires a human-readable title for all
        :ref:`wot_affordances` described. This property will generate a
        suitable string from either the name or the docstring.

        The title is either the first line of the docstring, or the name
        of the descriptor. Note that, if there's no summary line in the
        descriptor's instance docstring, or if ``__set__name__`` has not
        yet been called (i.e. if this attribute is accessed before the
        class on which the descriptor is defined has been fully set up),
        the `.NameNotSetError` from ``self.name`` will propagate, i.e.
        this property will either return a string or fail with an
        exception.

        Note also that, if the docstring for this descriptor is defined
        on the class rather than passed in (via a getter function or
        action function's docstring), it will also not be available until
        after ``__set_name__`` has been called.
        """
        if not self._title:
            # First, try to retrieve the first line of the docstring.
            # This is the preferred option for the title.
            self._title = get_summary(self)
        if not self._title:
            # If there's no docstring, or it doesn't have a summary line,
            # use the name of the descriptor instead.
            # Note that this will either succeed or raise an exception.
            self._title = self.name
        return self._title

    @property
    def description(self) -> str | None:
        """A description of the descriptor for use in documentation.

        This property will return the docstring describing the descriptor.
        As the first line of the docstring (if present) is used as the
        ``title`` in :ref:`gen_docs` it will be removed from this property.
        """
        return get_docstring(self, remove_summary=True)

    # I have ignored D105 (missing docstrings) on the overloads - these should not
    # exist on @overload definitions.
    @overload
    def __get__(self, obj: Owner, type: type | None = None) -> Value: ...

    @overload
    def __get__(self, obj: None, type: type) -> Self: ...

    def __get__(self, obj: Owner | None, type: type | None = None) -> Value | Self:
        """Return the value or the descriptor, as per `property`.

        If ``obj`` is ``None`` (i.e. the descriptor is accessed as a class attribute),
        we return the descriptor, i.e. ``self``.

        If ``obj`` is not ``None``, we return a value. To remove the need for this
        boilerplate in every subclass, we will call ``__instance_get__`` to get the
        value.

        :param obj: the `.Thing` instance to which we are attached.
        :param type: the `.Thing` subclass on which we are defined.

        :return: the value of the descriptor returned from ``__instance_get__`` when
            accessed on an instance, or the descriptor object if accessed on a class.
        """
        if obj is not None:
            return self.instance_get(obj)
        return self

    def instance_get(self, obj: Owner) -> Value:
        """Return the value of the descriptor.

        This method is called from ``__get__`` if the descriptor is accessed as an
        instance attribute. This means that ``obj`` is guaranteed to be present.

        ``__get__`` may be called on either an instance or a class, and if it is
        called on the class, the convention is that we should return the descriptor
        object (i.e. ``self``), as done by `builtins.property`.

        `.BaseDescriptor.__get__` takes care of this logic, so we need only consider
        the case where we are called as an instance attribute. This simplifies type
        annotations and removes the need for overload definitions in every subclass.

        :param obj: is the `.Thing` instance on which this descriptor is being
            accessed.
        :return: the value of the descriptor (i.e. property value, or bound method).

        :raises NotImplementedError: if it is not overridden.
        """
        raise NotImplementedError(
            "__instance_get__ must be defined on BaseDescriptor subclasses. \n\n"
            "See BaseDescriptor.__instance_get__ for details."
        )

    def __set__(self, obj: Owner, value: Value) -> None:
        """Mark the `BaseDescriptor` as a data descriptor.

        Even for read-only descriptors, it's important to define a ``__set__`` method.
        The presence of this method prevents Python overwriting the descriptor when
        a value is assigned. This base implementation returns an `AttributeError` to
        signal that the descriptor is read-only. Overriding it with a method that
        does not raise an exception will allow the descriptor to be written to.

        :param obj: The object on which to set the value.
        :param value: The value to set the descriptor to.
        :raises AttributeError: always, as this is read-only by default.
        """
        raise AttributeError("This attribute is read-only.")

    def _descriptor_info(
        self, info_class: type[DescriptorInfoT], obj: Owner | None = None
    ) -> DescriptorInfoT:
        """Return a `BaseDescriptorInfo` object for this descriptor.

        The return value of this function is an object that may be passed around
        without confusing type checkers, but still allows access to all of its
        functionality. Essentially, it just misses out ``__get__`` so that it
        is no longer a Descriptor.

        If ``owner`` is supplied, the returned object is bound to a particular
        object, and if not it is unbound, i.e. knows only about the class.

        :param info_class: the `.BaseDescriptorInfo` subclass to return.
        :param obj: The `.Thing` instance to which the return value is bound.
        :return: An object that may be used to refer to this descriptor.
        :raises RuntimeError: if garbage collection occurs unexpectedly. This
            should not happen and would indicate a LabThings bug.
        """
        if obj:
            return info_class(self, obj)
        else:
            self.assert_set_name_called()
            owning_class = self._owner_ref()
            if owning_class is None:
                raise RuntimeError("Class was unexpectedly deleted")
            return info_class(self, None, owning_class)

    def descriptor_info(
        self, owner: Owner | None = None
    ) -> BaseDescriptorInfo[Self, Owner, Value]:
        """Return a `BaseDescriptorInfo` object for this descriptor.

        This generates an object that refers to the descriptor, optionally
        bound to a particular object. It's intended to make it easier to pass
        around references to particular affordances, without needing to retrieve
        and store Descriptor objects directly (which gets confusing).
        If ``owner`` is supplied, the returned object is bound to a particular
        object, and if not it is unbound, i.e. knows only about the class.

        :param owner: The `.Thing` instance to which the return value is bound.
        :return: An object that may be used to refer to this descriptor.
        """
        return self._descriptor_info(BaseDescriptorInfo, owner)


class FieldTypedBaseDescriptorInfo(
    BaseDescriptorInfo[FTDescriptorT, Owner, Value],
    Generic[FTDescriptorT, Owner, Value],
):
    r"""A description of a `.FieldTypedBaseDescriptor`\ .

    This adds `value_type` to `.BaseDescriptorInfo` so we can fully describe a
    `.FieldTypedBaseDescriptor`\ .
    """

    @property
    def value_type(self) -> type[Value]:
        """The type of the descriptor's value."""
        return self.get_descriptor().value_type


class FieldTypedBaseDescriptor(Generic[Owner, Value], BaseDescriptor[Owner, Value]):
    """A BaseDescriptor that determines its type like a dataclass field."""

    def __init__(self) -> None:
        """Initialise the FieldTypedBaseDescriptor.

        Very little happens at initialisation time: most of the type determination
        happens in ``__set_name__`` and ``value_type`` so that type hints can
        be lazily evaluated.
        """
        super().__init__()
        self._type: type | None = None  # the type of the descriptor's value.
        # It may be set during __set_name__ if a type is available, or the
        # first time `self.value_type` is accessed.
        self._unevaluated_type_hint: str | None = None  # Set in `__set_name__`
        # Type hints are not un-stringized in `__set_name__` but we remember them
        # for later evaluation in `value_type`.

    def __set_name__(self, owner: type[Owner], name: str) -> None:
        r"""Take note of the name and type.

        This function is where we determine the type of the property. It may
        be specified in two ways: either by subscripting the descriptor
        or by annotating the attribute. This example is for ``DataProperty``
        as this class is not intended to be used directly.

        .. code-block:: python

            class MyThing(Thing):
                subscripted_property = DataProperty[int](default=0)
                annotated_property: int = DataProperty(default=0)

        The second form often works better with autocompletion, though it
        is usually called via a function to avoid type checking errors.

        Neither form allows us to access the type during ``__init__``, which
        is why we find the type here. If there is a problem, exceptions raised
        will appear to come from the class definition, so it's important to
        include the name of the attribute.

        See :ref:`descriptors` for links to the Python docs about when
        this function is called.

        For subscripted types (i.e. the first form above), we use
        `typing.get_args` to retrieve the value type. This will be evaluated
        immediately, resolving any forward references.

        We use `typing.get_type_hints` to resolve type hints on the owning
        class. This takes care of a lot of subtleties like un-stringifying
        forward references. In order to support forward references, we only
        check for the existence of a type hint during ``__set_name__`` and
        will evaluate it fully during ``value_type``\ .

        :param owner: the `.Thing` subclass to which we are being attached.
        :param name: the name to which we have been assigned.

        :raises InconsistentTypeError: if the type is specified twice and
            the two types are not identical.
        :raises MissingTypeError: if no type hints have been given.
        """
        # Call BaseDescriptor so we remember the name
        super().__set_name__(owner, name)

        # Check for type subscripts
        if hasattr(self, "__orig_class__"):
            # We have been instantiated with a subscript, e.g. BaseProperty[int].
            #
            # __orig_class__ is set on generic classes when they are instantiated
            # with a subscripted type. It is not available during __init__, which
            # is why we check for it here.
            self._type = typing.get_args(self.__orig_class__)[1]
            if isinstance(self._type, typing.ForwardRef):
                raise MissingTypeError(
                    f"{owner}.{name} is a subscripted descriptor, where the "
                    f"subscript is a forward reference ({self._type}). Forward "
                    "references are not supported as subscripts."
                )

        # Check for annotations on the parent class
        field_annotation = inspect.get_annotations(owner).get(name, None)
        if field_annotation is not None:
            # We have been assigned to an annotated class attribute, e.g.
            # myprop: int = BaseProperty(0)
            if self._type is not None and self._type != field_annotation:
                # As a rule, if _type is already set, we don't expect any
                # annotation on the attribute, so this error should not
                # be a frequent occurrence.
                raise InconsistentTypeError(
                    f"Property {name} on {owner} has conflicting types.\n\n"
                    f"The field annotation of {field_annotation} conflicts "
                    f"with the inferred type of {self._type}."
                )
            self._unevaluated_type_hint = field_annotation

        # Ensure a type is specified.
        # If we've not set _type by now, we are not going to set it, and the
        # descriptor will not work properly. It's best to raise an error now.
        # Note that we need to specify the attribute name, as the exception
        # will appear to come from the end of the class definition, and not
        # from the descriptor definition.
        if self._type is None and self._unevaluated_type_hint is None:
            raise MissingTypeError(
                f"No type hint was found for attribute {name} on {owner}."
            )

    @builtins.property
    def value_type(self) -> type[Value]:
        """The type of this descriptor's value.

        This is only available after ``__set_name__`` has been called, which happens
        at the end of the class definition. If it is called too early, a
        `.DescriptorNotAddedToClassError` will be raised.

        Accessing this property will attempt to resolve forward references,
        i.e. type annotations that are strings. If there is an error resolving
        the forward reference, a `.MissingTypeError` will be raised.

        :return: the type of the descriptor's value.
        :raises MissingTypeError: if the type is None, not resolvable, or not specified.
        """
        self.assert_set_name_called()
        if self._type is None and self._unevaluated_type_hint is not None:
            # We have a forward reference, so we need to resolve it.
            if self._owner_ref is None:
                raise MissingTypeError(
                    f"Can't resolve forward reference for type of {self.name} because "
                    "the class on which it was defined wasn't saved. This is a "
                    "LabThings bug - please report it."
                )
            # `self._owner_ref` is set in `BaseDescriptor.__set_name__`.
            owner = self._owner_ref()
            if owner is None:
                raise MissingTypeError(
                    f"Can't resolve forward reference for type of {self.name} because "
                    "the class on which it was defined has been garbage collected."
                )
            try:
                # Resolving a forward reference has quirks, and rather than tie us
                # to undocumented implementation details of `typing` we just use
                # `typing.get_type_hints`.
                # This isn't efficient (it resolves everything, rather than just
                # the one annotation we need, and it traverses the MRO when we know
                # the class we're defined on) but it is part of the public API,
                # and therefore much less likely to break.
                #
                # Note that we already checked there was an annotation in
                # __set_name__.
                hints = typing.get_type_hints(owner, include_extras=True)
                self._type = hints[self.name]
            except Exception as e:
                raise MissingTypeError(
                    f"Can't resolve forward reference for type of {self.name}."
                ) from e
        if self._type is None:
            # We should never reach this line: if `__set_name__` was called, we'd
            # have raised an exception there if _type was None. If `__set_name__`
            # has not been called, `self.assert_set_name_called()` would have failed.
            # This block is required for `mypy` to know that self._type is not None.
            raise MissingTypeError(
                f"No type hint was found for property {self.name}. This may indicate "
                "a bug in LabThings, as the error should have been caught before now."
            )

        return self._type

    def descriptor_info(
        self, owner: Owner | None = None
    ) -> FieldTypedBaseDescriptorInfo[Self, Owner, Value]:
        """Return a `BaseDescriptorInfo` object for this descriptor.

        This generates an object that refers to the descriptor, optionally
        bound to a particular object. It's intended to make it easier to pass
        around references to particular affordances, without needing to retrieve
        and store Descriptor objects directly (which gets confusing).
        If ``owner`` is supplied, the returned object is bound to a particular
        object, and if not it is unbound, i.e. knows only about the class.

        :param owner: The `.Thing` instance to which the return value is bound.
        :return: An object that may be used to refer to this descriptor.
        """
        return self._descriptor_info(FieldTypedBaseDescriptorInfo, owner)


class DescriptorInfoCollection(
    Mapping[str, DescriptorInfoT],
    OptionallyBoundInfo[Owner],
    Generic[Owner, DescriptorInfoT],
):
    """Easy access to DescriptorInfo objects of a particular type.

    This class works as a Mapping, so you can retrieve individual
    `.DescriptorInfo` objects by name, or iterate over the names of
    the descriptors.

    It may be initialised with an object, in which case the contained
    `.DescriptorInfo` objects will be bound to that object. If initialised
    without an object, the contained `.DescriptorInfo` objects will be
    unbound, i.e. referring only to the class.

    This class is subclassed by each of the LabThings descriptors
    (Properties, Actions, etc.) and generated by a corresponding
    `.OptionallyBoundDescriptor` on `.Thing` for convenience.
    """

    def __init__(
        self,
        obj: Owner | None,
        cls: type[Owner] | None = None,
    ) -> None:
        r"""Initialise the DescriptorInfoCollection.

        This initialises the object, optionally binding it to `obj` if it is
        not `None`\ .

        :param obj: The object to which this info object is bound. If
            it is `None` (default), the object will be unbound and will refer to
            the descriptor as attached to the class. This may mean that some
            methods are unavailable.

        :param cls: The class to which this info object refers. May be omitted
            if `obj` is supplied.
        """
        super().__init__(obj, cls)

    _descriptorinfo_class: type[DescriptorInfoT]
    """The class of DescriptorInfo objects contained in this collection.

    This class attribute must be set in subclasses.
    """

    @property
    def descriptorinfo_class(self) -> type[DescriptorInfoT]:
        """The class of DescriptorInfo objects contained in this collection."""
        return self._descriptorinfo_class

    def __getitem__(self, key: str) -> DescriptorInfoT:
        """Retrieve a DescriptorInfo object given the name of the descriptor.

        :param key: The name of the descriptor whose info object is required.
        :return: The DescriptorInfo object for the named descriptor.
        :raises KeyError: if the key does not refer to a descriptor of the right
            type.
        """
        attr = getattr(self.owning_class, key, None)
        if isinstance(attr, BaseDescriptor):
            info = attr.descriptor_info(self.owning_object)
            if isinstance(info, self.descriptorinfo_class):
                return info
        # Attributes that are missing or of the wrong type are not present in
        # the mapping, so they raise KeyError.
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        """Iterate over the names of the descriptors of the specified type.

        :yield: The names of the descriptors.
        """
        for name, member in inspect.getmembers(self.owning_class):
            if isinstance(member, BaseDescriptor):
                if isinstance(member.descriptor_info(), self._descriptorinfo_class):
                    yield name

    def __len__(self) -> int:
        """Return the number of descriptors of the specified type.

        :return: The number of descriptors of the specified type.
        """
        return sum(1 for _ in self.__iter__())


class OptionallyBoundDescriptor(Generic[Owner, OptionallyBoundInfoT]):
    """A descriptor that will return an OptionallyBoundInfo object.

    This descriptor will return an instance of a particular class, initialised
    with either the object, or its class, depending on how it is accessed.

    This is useful for returning collections of `.BaseDescriptorInfo` objects
    from a `.Thing` subclass.
    """

    def __init__(self, cls: type[OptionallyBoundInfoT]) -> None:
        """Initialise the descriptor.

        :param cls: The class of `.OptionallyBoundInfo` objects that this descriptor
            will return.
        """
        super().__init__()
        self._cls = cls

    def __get__(
        self,
        obj: Owner | None,
        cls: type[Owner] | None = None,
    ) -> OptionallyBoundInfoT:
        """Return an OptionallyBoundInfo object.

        :param obj: The object to which the info is bound, or `None`
            if unbound.
        :param cls: The class on which the info is defined.

        :return: An `OptionallyBoundInfo` object.
        """
        return self._cls(obj, cls)


# get_class_attribute_docstrings is a relatively expensive function that
# will be called potentially quite a few times on the same class. It will
# return the same result each time (because it depends only on the source
# code of the class, which can't change), so it makes sense to cache it.
#
# We use weak keys to avoid messing up garbage collection, and cache the
# mapping of attribute names to attribute docstrings.
_class_attribute_docstring_cache: WeakKeyDictionary[type, Mapping[str, str]] = (
    WeakKeyDictionary()
)


def get_class_attribute_docstrings(cls: type) -> Mapping[str, str]:
    """Retrieve docstrings for the attributes of a class.

    Python formally supports ``__doc__`` attributes on classes and functions, and
    this means that classes and methods can self-describe in a way that is picked
    up by documentation tools. There isn't currently a language feature specifically
    provided to annotate other attributes of a class, but there is a convention
    that seems almost universally adopted by documentation tools, which is to
    add a string literal immediately after the attribute assignment. While it's
    not a formal language feature, Python does explicitly allow these string
    literals (which don't have any other purpose) to enable documentation tools
    to document attributes.

    This function inspects a class, and returns a dictionary mapping attribute
    names to docstrings, where the docstring is a string immediately following
    the attribute. For example:

    .. code-block:: python

        class Example:
            my_constant: int = 10
            "A number that is all mine."


        docs = get_class_attribute_docstrings(Example)

        assert docs["my_constant"] == "A number that is all mine."


    .. note::

        This function relies on re-parsing the source of the class, so it will
        not work on classes that are not defined in a file (for example, if you
        just paste the example above into a Python interpreter). In that case,
        an empty dictionary is returned.

        The same limitation means dynamically defined classes will result in
        an empty dictionary.

    .. note::

        This function uses a cache, so subsequent calls on the same class will
        return a cached value. As dynamic classes are not supported, this is
        not expected to be a problem.

    :param cls: The class to inspect
    :return: A mapping of attribute names to docstrings. Note that this will be
        wrapped in a `types.MappingProxyType` to prevent accidental modification.

    :raises TypeError: if the supplied object is not a class.
    """
    # For a helpful article on how this works, see:
    # https://davidism.com/attribute-docstrings/
    if cls in _class_attribute_docstring_cache:  # Attempt to use the cache
        return _class_attribute_docstring_cache[cls]

    # We start by getting hold of the source code of our class. This requires
    # the class to be loaded from a file, which is nearly always the case.
    # We will simply return an empty dictionary if this fails: there is never
    # any guarantee docstrings are available.
    try:
        src = inspect.getsource(cls)
    except (OSError, AttributeError):
        # An OSError is raised if the source is not available.
        # An AttributeError is raised if the source was loaded from
        # a WindowsPath object, perhaps using ``runpy``
        return {}
    # The line below parses the class to get a syntax tree.
    module_ast = ast.parse(textwrap.dedent(src))
    class_def = module_ast.body[0]
    if not isinstance(class_def, ast.ClassDef):
        raise TypeError("The object supplied was not a class.")
    # Work through each pair of nodes, looking for an assignment followed by
    # a string.
    docs: dict[str, str] = {}
    for a, b in pairwise(class_def.body):
        if not isinstance(a, ast.Assign | ast.AnnAssign):
            continue  # The first node isn't an assignment
        if (
            not isinstance(b, ast.Expr)
            or not isinstance(b.value, ast.Constant)
            or not isinstance(b.value.value, str)
        ):
            continue  # The second node must be a string constant

        # Assignments may have multiple targets (a=b=c) so we
        # need to cope with a list of targets.
        if isinstance(a, ast.Assign):
            targets = a.targets
        else:  # Annotated assignments have only one target, so make it a list.
            targets = [a.target]

        # Clean up the docstring as per the usual rules
        doc = inspect.cleandoc(b.value.value)

        for target in targets:
            if not isinstance(target, ast.Name):
                # We only care about things assigned to plain names. Assignment to
                # attributes of objects, or items in dictionaries, are irrelevant.
                continue
            docs[target.id] = doc

    _class_attribute_docstring_cache[cls] = MappingProxyType(docs)
    return _class_attribute_docstring_cache[cls]
