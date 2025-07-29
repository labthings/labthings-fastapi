"""A base class for descriptors in LabThings.

:ref:`descriptors` are used to describe :ref:`wot_affordances` in LabThings-FastAPI.
There is some behaviour common to most of these, and `.BaseDescriptor` centralises
the code that implements it.
"""

from __future__ import annotations
from typing import overload, Generic, Self, TypeVar, TYPE_CHECKING

from .utilities.introspection import get_summary

if TYPE_CHECKING:
    from .thing import Thing

Value = TypeVar("Value")
"""The value returned by the descriptor, when called on an instance."""


class DescriptorNotAddedToClassError(RuntimeError):
    """Descriptor has not yet been added to a class.

    This error is raised if certain properties of descriptors are accessed
    before ``__set_name__`` has been called on the descriptor.  ``__set_name``
    is part of the descriptor protocol, and is called when a class is defined
    to notify the descriptor of its name and owning class.

    If you see this error, it often means that a descriptor has been instantiated
    but not attached to a class, for example:

    .. code-block:: python

        import labthings as lt


        class Test(lt.Thing):
            myprop: int = lt.property(0)  # This is OK


        orphaned_prop: int = lt.property(0)  # Not OK

        Test.myprop.model  # Evaluates to a pydantic model

        orphaned_prop.model  # Raises this exception
    """


class BaseDescriptor(Generic[Value]):
    r"""A base class for descriptors in LabThings-FastAPI.

    This class implements several behaviours common to descriptors in LabThings:

    * The descriptor remembers the name it's assigned to in ``name``, for use in
        :ref:`gen_docs`\ .
    * When called as a class attribute, the descriptor returns itself, as done by
        e.g. `property`.
    """

    def __init__(self) -> None:
        """Initialise a BaseDescriptor."""
        self._name: str | None = None
        self._title: str | None = None
        self._description: str | None = None
        # We set the instance __doc__ to None so the descriptor class docstring
        # doesn't get picked up by OpenAPI/Thing Description.
        self.__doc__ = None
        # We explicitly check when __set_name__ is called, so we can raise helpful
        # errors
        self._set_name_called: bool = False

    def __set_name__(self, owner: type[Thing], name: str) -> None:
        r"""Take note of the name to which the descriptor is assigned.

        This is called when the descriptor is assigned to an attribute of a class.
        This function just remembers the name, so it can be used in
        :ref:`gen_docs`\ .

        :param owner: the `.Thing` subclass to which we are being attached.
        :param name: the name to which we have been assigned.
        """
        # Remember the name to which we're assigned. Accessed by the read only
        # property ``name``.
        self._name = name
        self._set_name_called = True

    def assert_set_name_called(self):
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
        """
        self.assert_set_name_called()
        assert self._name is not None
        # The assert statement is mostly for typing: if assert_set_name_called
        # doesn't raise an error, self._name has been set.
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

    # I have ignored D105 (missing docstrings) on the overloads - these should not
    # exist on @overload definitions.
    @overload
    def __get__(self, obj: Thing, type: type | None = None) -> Value: ...  # noqa: D105

    @overload
    def __get__(self, obj: None, type: type) -> Self: ...  # noqa: D105

    def __get__(self, obj: Thing | None, type: type | None = None) -> Value | Self:
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

    def instance_get(self, obj: Thing) -> Value:
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
