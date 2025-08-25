"""A base class for descriptors in LabThings.

:ref:`descriptors` are used to describe :ref:`wot_affordances` in LabThings-FastAPI.
There is some behaviour common to most of these, and `.BaseDescriptor` centralises
the code that implements it.
"""

from __future__ import annotations
import ast
import inspect
from itertools import pairwise
import textwrap
from typing import overload, Generic, Mapping, TypeVar, TYPE_CHECKING
from types import MappingProxyType
from weakref import WeakKeyDictionary
from typing_extensions import Self

from .utilities.introspection import get_docstring, get_summary

if TYPE_CHECKING:
    from .thing import Thing

Value = TypeVar("Value")
"""The value returned by the descriptor, when called on an instance."""


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
            def set_prop4(self, val):
                "A setter for prop4 that is not named prop4."
                pass

    .. note::

        Because this exception is raised in ``__set_name__`` it will not
        appear to come from the descriptor assignment, but instead it will
        be raised at the end of the class definition. The descriptor name(s)
        should be in the error message.

    """


class BaseDescriptor(Generic[Value]):
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

    def __set_name__(self, owner: type[Thing], name: str) -> None:
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
