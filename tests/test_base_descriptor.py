import gc
import pytest
from labthings_fastapi.base_descriptor import (
    BaseDescriptor,
    BaseDescriptorInfo,
    DescriptorInfoCollection,
    FieldTypedBaseDescriptor,
    DescriptorNotAddedToClassError,
    DescriptorAddedToClassTwiceError,
    FieldTypedBaseDescriptorInfo,
    OptionallyBoundDescriptor,
    OptionallyBoundInfo,
    get_class_attribute_docstrings,
)
from labthings_fastapi.testing import create_thing_without_server
from .utilities import raises_or_is_caused_by
from labthings_fastapi.exceptions import (
    MissingTypeError,
    InconsistentTypeError,
    NotBoundToInstanceError,
)
import labthings_fastapi as lt


class MockProperty(BaseDescriptor[lt.Thing, str]):
    """A mock property class."""

    # The line below isn't defined on a `Thing`, so mypy
    # errors - but we ignore this for testing.
    def instance_get(self, _obj) -> str:
        """This is called by BaseProperty.__get__."""
        return "An example value."


class Example:
    """A class containing some attributes that may or may not have docstrings.

    We will use code in `base_descriptor` to inspect this class and test it finds
    the right docstrings.
    """

    my_constant: int = 10
    "A number that is all mine."

    my_undocumented_constant: int = 20

    my_property = MockProperty()
    "Docs for my_property."

    my_undocumented_property = MockProperty()

    my_property_with_nice_docs = MockProperty()
    """Title goes here.
    
    The docstring should have a one-line title followed by
    a body giving a longer description of what's going on.
    """

    my_property_with_only_description = MockProperty()
    """
    This is a poorly formatted docstring that does not have
    a one-line title. It should result in the property name
    being used as a title, and this text as description.
    """

    # This line looks like an attribute assignment with a docstring,
    # but it's not - because we are not assigning to a simple name.
    # This tests that such assignments won't cause errors.
    my_property_with_nice_docs.attribute = "dummy value"
    """A spurious docstring."""

    # As above, this is testing that we safely ignore assignments
    # that are not to simple names. The code below should not
    # cause an error, but will cause a ``continue`` statement
    # to skip actions, testing another code path when the
    # class is analysed.
    dict_attribute = {}
    dict_attribute["foo"] = "bar"
    """Here is a spurious docstring that should be ignored."""

    base_descriptor = BaseDescriptor()
    """This descriptor should raise NotImplementedError."""


def test_docstrings_are_retrieved():
    """Check that the docstring can be picked up from the class definition.

    This test checks that:
    * We get docstrings for exactly the attributes we expect.
    * The one-line docstrings are picked up correctly.
    * The docstring-inspection code isn't confused by spurious docstrings
      next to assignments that are not to simple names. (see comments on
      the class definition of `Example`).

    Detection and interpretation of multiline docstrings is tested in
    `test_basedescriptor_with_good_docstring`.
    """
    docs = get_class_attribute_docstrings(Example)
    assert docs["my_constant"] == "A number that is all mine."
    assert docs["my_property"] == "Docs for my_property."
    expected_names = [
        "my_constant",
        "my_property",
        "my_property_with_nice_docs",
        "my_property_with_only_description",
        "base_descriptor",
    ]
    assert set(docs.keys()) == set(expected_names)


def test_non_classes_raise_errors():
    """Check we validate the input object.

    If `get_class_attribute_docstrings` is called on something other than
    a class, we should raise an error.
    """

    def dummy():
        pass

    with pytest.raises(TypeError):
        get_class_attribute_docstrings(dummy)


def test_uncheckable_class():
    """Check we don't crash if we can't check a class.

    If `inspect.getsource` fails, we should return an empty dict.
    """
    MyClass = type("MyClass", (), {"intattr": 10})
    doc = get_class_attribute_docstrings(MyClass)
    assert doc == {}


def test_docstrings_are_cached():
    """Check that the docstrings aren't being regenerated every time."""
    docs1 = get_class_attribute_docstrings(Example)
    docs2 = get_class_attribute_docstrings(Example)
    # The dictionary of attribute docstrings is cached, keyed on the
    # class. The test below checks the same object is returned, not
    # just one with the same values in it - this implies the cache
    # is working.
    assert docs1 is docs2


def test_basedescriptor_with_good_docstring():
    """Check we get the right documentation properties."""
    prop = Example.my_property_with_nice_docs
    assert prop.name == "my_property_with_nice_docs"
    assert prop.title == "Title goes here."
    assert prop.description.startswith("The docstring")


def test_basedescriptor_with_oneline_docstring():
    """Check we get the right documentation properties for a one-liner."""
    prop = Example.my_property
    assert prop.name == "my_property"
    assert prop.title == "Docs for my_property."
    assert prop.description.startswith("Docs for my_property.")


def test_basedescriptor_with_bad_multiline_docstring():
    """Check a docstring with no title produces the expected result.

    A multiline docstring with no title (i.e. no blank second line)
    should result in the whole docstring being used as the description.
    """
    prop = Example.my_property_with_only_description
    assert prop.name == "my_property_with_only_description"
    assert prop.title == "This is a poorly formatted docstring that does not have"
    assert prop.description.startswith("This is a poorly formatted")


def test_basedescriptor_orphaned():
    """Check the right error is raised if we ask for the name outside a class."""
    prop = MockProperty()
    with pytest.raises(DescriptorNotAddedToClassError):
        _ = prop.name


def test_basedescriptor_fallback():
    """Check the title defaults to the name."""
    p = Example.my_undocumented_property
    assert p.title == "my_undocumented_property"
    assert p.__doc__ is None
    assert p.description is None


def test_basedescriptor_get():
    """Check the __get__ function works

    BaseDescriptor provides an implementation of __get__ that
    returns the descriptor when accessed as a class attribute,
    and calls `instance_get` when accessed as the attribute of
    an instance. This test checks both those scenarios.
    """
    e = Example()
    assert e.my_property == "An example value."
    assert isinstance(Example.my_property, MockProperty)
    with pytest.raises(NotImplementedError):
        # BaseDescriptor requires `instance_get` to be overridden.
        _ = e.base_descriptor


class MockFunctionalProperty(MockProperty):
    """A mock property class with a setter decorator.

    This class is used by test_decorator_different_names.
    """

    def __init__(self, fget):
        """Add a mock getter and initialise variables."""
        super().__init__()
        self._getter = fget
        self._setter = None
        self._names = []

    def setter(self, fset):
        """Can be used as a decorator to add a setter."""
        self._setter = fset
        return self

    def __set_name__(self, owner, name):
        """Check how many times __set_name__ is called."""
        self._names.append(name)
        super().__set_name__(owner, name)


def test_decorator_different_names():
    """Check that adding a descriptor to a class twice raises the right error.

    Much confusion will result if a ``BaseDescriptor`` is added to a class twice
    or added to two different classes. This test checks an error is raised when
    that happens.

    Note that there is an exception to this in `.FunctionalProperty` and that
    exception is tested in ``test_property.py`` in this folder.
    """
    # First, very obviously double-assign a BaseDescriptor
    with raises_or_is_caused_by(DescriptorAddedToClassTwiceError) as excinfo:

        class ExplicitExample:
            """An example class."""

            prop1 = BaseDescriptor()
            prop2 = prop1

    # The exception occurs at the end of the class definition, so check we include
    # the property names.
    assert "prop1" in str(excinfo.value)
    assert "prop2" in str(excinfo.value)

    # The next form of properties works and doesn't trigger the error, but is
    # flagged (arguably spuriously) as an error by mypy.
    class ValidExceptInMyPy:
        """An example class that fails type checking but is valid Python."""

        @MockFunctionalProperty
        def prop1(self):
            return False

        @prop1.setter
        def prop1(self, val):
            pass

    # This workaround satisfies MyPy but double-assigns the descriptor.
    # It should raise an error here, but is a special case in
    # `.FunctionalProperty.__set_name__` so will be OK for `.FunctionalProperty`
    # and `.FunctionalSetting` as a result.
    with raises_or_is_caused_by(DescriptorAddedToClassTwiceError) as excinfo:

        class DecoratorExample:
            """Another example class."""

            @MockFunctionalProperty
            def prop1(self):
                return False

            @prop1.setter
            def _set_prop1(self, val):
                pass

    # The exception occurs at the end of the class definition, so check we include
    # the property names.
    assert "prop1" in str(excinfo.value)
    assert "_set_prop1" in str(excinfo.value)

    # For good measure, check reuse across classes is also prevented.
    class FirstExampleClass:
        prop = BaseDescriptor()

    with raises_or_is_caused_by(DescriptorAddedToClassTwiceError) as excinfo:

        class SecondExampleClass:
            prop = FirstExampleClass.prop

    # The message should mention names and classes
    assert "prop" in str(excinfo.value)
    assert "FirstExampleClass" in str(excinfo.value)
    assert "SecondExampleClass" in str(excinfo.value)


class CustomType:
    """A custom datatype."""

    pass


class FieldTypedExample:
    """An example with field-typed descriptors."""

    int_or_str_prop: int | str = FieldTypedBaseDescriptor()
    int_or_str_subscript = FieldTypedBaseDescriptor[lt.Thing, int | str]()
    int_or_str_stringified: "int | str" = FieldTypedBaseDescriptor()
    customprop: CustomType = FieldTypedBaseDescriptor()
    customprop_subscript = FieldTypedBaseDescriptor[lt.Thing, CustomType]()
    futureprop: "FutureType" = FieldTypedBaseDescriptor()


class FutureType:
    """A custom datatype, defined after the descriptor."""

    pass


@pytest.mark.parametrize(
    ("name", "value_type"),
    [
        ("int_or_str_prop", int | str),
        ("int_or_str_subscript", int | str),
        ("int_or_str_stringified", int | str),
        ("customprop", CustomType),
        ("customprop_subscript", CustomType),
        ("futureprop", FutureType),
    ],
)
def test_fieldtyped_definition(name, value_type):
    """Test that field-typed descriptors pick up their type correctly."""
    prop = getattr(FieldTypedExample, name)
    assert prop.name == name
    assert prop.value_type == value_type


def test_fieldtyped_missingtype():
    """Check the right error is raised when no type can be found."""
    with raises_or_is_caused_by(MissingTypeError) as excinfo:

        class Example2:
            field2 = FieldTypedBaseDescriptor()

    msg = str(excinfo.value)
    assert msg.startswith("No type hint was found")
    # We check the field name is included, because the exception will
    # arise from the end of the class definition, rather than the line
    # where the field is defined.
    assert "field2" in msg

    # This one defines OK, but should error when we access its type.
    # Note that Ruff already spots the bad forward reference, hence the
    # directive to ignore F821.
    class Example3:
        field3: "BadForwardReference" = FieldTypedBaseDescriptor()  # noqa: F821
        field4: "int" = FieldTypedBaseDescriptor()
        field5: "int" = FieldTypedBaseDescriptor()

    with pytest.raises(MissingTypeError) as excinfo:
        _ = Example3.field3.value_type

    msg = str(excinfo.value)
    assert "resolve forward ref" in msg
    assert "field3" in msg

    # If we try to resolve a forward reference and the owner is None, it
    # should raise an error.
    # I don't see how this could happen in practice, _owner is always
    # set if we find a forward reference.
    # We force this error condition by manually setting _owner to None
    Example3.field4._owner_ref = None

    with pytest.raises(MissingTypeError) as excinfo:
        _ = Example3.field4.value_type

    msg = str(excinfo.value)
    assert "resolve forward ref" in msg
    assert "wasn't saved" in msg
    assert "field4" in msg

    # We reuse field4 but manually set _type and _unevaluated_type_hint
    # to None, to test the catch-all error
    Example3.field4._unevaluated_type_hint = None
    Example3.field4._type = None

    with pytest.raises(MissingTypeError) as excinfo:
        _ = Example3.field4.value_type

    msg = str(excinfo.value)
    assert "bug in LabThings" in msg
    assert "caught before now" in msg
    assert "field4" in msg

    # If the class is finalised before we evaluate type hints, we should
    # get a MissingTypeError. This probably only happens on dynamically
    # generated classes, and I think it's unlikely we'd dynamically generate
    # Thing subclasses in a way that they go out of scope.
    prop = Example3.field5
    del Example3
    gc.collect()

    with pytest.raises(MissingTypeError) as excinfo:
        _ = prop.value_type

    msg = str(excinfo.value)
    assert "resolve forward ref" in msg
    assert "garbage collected" in msg
    assert "field5" in msg

    # Rather than roll my own evaluator for forward references, we just
    # won't support forward references in subscripted types for now.
    with raises_or_is_caused_by(MissingTypeError) as excinfo:

        class Example4:
            field6 = FieldTypedBaseDescriptor[lt.Thing, "str"]()

    msg = str(excinfo.value)
    assert "forward reference" in msg
    assert "not supported as subscripts"
    assert "field6" in msg


def test_mismatched_types():
    """Check two type hints that don't match raises an error."""
    with raises_or_is_caused_by(InconsistentTypeError):

        class Example3:
            field: int = FieldTypedBaseDescriptor[lt.Thing, str]()


def test_double_specified_types():
    """Check two type hints that match are allowed.

    This is a very odd thing to do, but it feels right to allow
    it, provided the types are an exact match.
    """

    class Example4:
        field: int | None = FieldTypedBaseDescriptor[lt.Thing, int | None]()

    assert Example4.field.value_type == int | None


def test_stringified_vs_unstringified_mismatch():
    """Test that string type hints don't match non-string ones.

    This behaviour may change in the future - but this test is here
    to make sure that, if it does, we are changing it deliberately.
    If a descriptor is typed using both a subscript and a field
    annotation, they should match -
    """
    with raises_or_is_caused_by(InconsistentTypeError):

        class Example5:
            field: "int" = FieldTypedBaseDescriptor[lt.Thing, int]()


def test_optionally_bound_info():
    """Test the OptionallyBoundInfo base class."""

    class Example6(lt.Thing):
        pass

    class Example6a(lt.Thing):
        pass

    example6 = create_thing_without_server(Example6)

    bound_info = OptionallyBoundInfo(example6)
    assert bound_info.owning_object is example6
    assert bound_info.owning_object_or_error() is example6
    assert bound_info.owning_class is Example6
    assert bound_info.is_bound is True

    unbound_info = OptionallyBoundInfo(None, Example6)
    assert unbound_info.owning_object is None
    with pytest.raises(NotBoundToInstanceError):
        unbound_info.owning_object_or_error()
    assert unbound_info.owning_class is Example6
    assert unbound_info.is_bound is False

    # Check that we can't create it with a bad class
    with pytest.raises(TypeError):
        _ = OptionallyBoundInfo(example6, Example6a)

    # Check that we can't create it with no class or object
    with pytest.raises(ValueError):
        _ = OptionallyBoundInfo(None, None)  # type: ignore


def test_descriptorinfo(mocker):
    """Test that the DescriptorInfo object works as expected."""

    class Example7:
        intfield: int = FieldTypedBaseDescriptor()
        """The descriptor's title.
        
        A description from a multiline docstring.
        """

        strprop = BaseDescriptor["Example7", str]()

    intfield_descriptor = Example7.intfield
    assert isinstance(intfield_descriptor, FieldTypedBaseDescriptor)

    # Test it can't be instantiated without either a class or an object
    # Instantiation with class/object is done implicitly by the
    # blocks below.
    with pytest.raises(ValueError, match="must be supplied"):
        _ = BaseDescriptorInfo(intfield_descriptor, None)

    # First, make an unbound info object
    intfield_info = intfield_descriptor.descriptor_info()
    assert repr(intfield_info) == "<FieldTypedBaseDescriptorInfo for Example7.intfield>"
    assert intfield_info.is_bound is False
    assert intfield_info.name == "intfield"
    assert intfield_info.title == "The descriptor's title."
    assert intfield_info.description == "A description from a multiline docstring."
    with pytest.raises(NotBoundToInstanceError):
        intfield_info.get()
    with pytest.raises(NotBoundToInstanceError):
        intfield_info.set(10)

    # Next, check the bound version
    example6 = Example7()
    intfield_info = intfield_descriptor.descriptor_info(example6)
    assert repr(intfield_info).startswith(
        "<FieldTypedBaseDescriptorInfo for Example7.intfield bound to <"
    )
    assert intfield_info.is_bound is True
    assert intfield_info.name == "intfield"
    assert intfield_info.title == "The descriptor's title."
    assert intfield_info.description == "A description from a multiline docstring."
    with pytest.raises(NotImplementedError):
        # As we're now calling on a bound info object, we should just get the
        # exception from `BaseDescriptor.instance_get()`, not the unbound error.
        intfield_info.get()
    with pytest.raises(AttributeError, match="read-only"):
        # As we're now calling on a bound info object, we should just get the
        # exception from `BaseDescriptor.__set__(value)`, not the unbound error.
        intfield_info.set(10)
    assert intfield_info.value_type is int

    # Check strprop, which is missing most of the documentation properties and
    # should not have a value_type.
    strprop_descriptor = Example7.strprop
    assert isinstance(strprop_descriptor, BaseDescriptor)
    strprop_info = strprop_descriptor.descriptor_info()
    assert strprop_info.name == "strprop"
    assert strprop_info.title.lower() == "strprop"
    assert strprop_info.description is None
    with pytest.raises(AttributeError):
        _ = strprop_info.value_type

    assert intfield_info == intfield_info
    assert intfield_info != strprop_info


def test_descriptorinfocollection():
    """Test the DescriptorInfoCollection class.

    This test checks that:
    * We can get a collection of all descriptors on a Thing subclass.
    * The collection contains the right names (is filtered by type).
    * The individual DescriptorInfo objects in the collection have the
      right properties.
    * The `OptionallyBoundDescriptor` returns a collection on either the
      class or the instance, bound or unbound as appropriate.
    """

    class BaseDescriptorInfoCollection(
        DescriptorInfoCollection[lt.Thing, BaseDescriptorInfo]
    ):
        """A collection of BaseDescriptorInfo objects."""

        _descriptorinfo_class = BaseDescriptorInfo

    class FieldTypedBaseDescriptorInfoCollection(
        DescriptorInfoCollection[lt.Thing, FieldTypedBaseDescriptorInfo]
    ):
        """A collection of FieldTypedBaseDescriptorInfo objects."""

        _descriptorinfo_class = FieldTypedBaseDescriptorInfo

    class Example8(lt.Thing):
        intfield: int = FieldTypedBaseDescriptor()
        """An integer field."""

        strprop = BaseDescriptor["Example8", str]()
        """A string property."""

        another_intfield: int = FieldTypedBaseDescriptor()
        """Another integer field."""

        base_descriptors = OptionallyBoundDescriptor(BaseDescriptorInfoCollection)
        """A mapping of all base descriptors."""

        field_typed_descriptors = OptionallyBoundDescriptor(
            FieldTypedBaseDescriptorInfoCollection
        )
        """A mapping of all field-typed descriptors."""

    # The property should return a mapping of names to descriptor info objects
    collection = Example8.base_descriptors
    assert isinstance(collection, DescriptorInfoCollection)

    names = list(collection)
    assert set(names) == {"intfield", "strprop", "another_intfield"}
    assert len(collection) == 3
    assert collection.is_bound is False

    intfield_info = collection["intfield"]
    assert isinstance(intfield_info, FieldTypedBaseDescriptorInfo)
    assert intfield_info.name == "intfield"
    assert intfield_info.title == "An integer field."
    assert intfield_info.value_type is int
    assert intfield_info.is_bound is False

    strprop_info = collection["strprop"]
    assert strprop_info.name == "strprop"
    assert strprop_info.title == "A string property."
    with pytest.raises(AttributeError):
        _ = strprop_info.value_type  # type: ignore
    assert strprop_info.is_bound is False

    # A more specific descriptor info type should narrow the collection
    field_typed_collection = Example8.field_typed_descriptors
    assert isinstance(field_typed_collection, DescriptorInfoCollection)
    names = list(field_typed_collection)
    assert set(names) == {"intfield", "another_intfield"}
    assert len(field_typed_collection) == 2

    assert field_typed_collection["intfield"] == intfield_info
    assert field_typed_collection["another_intfield"] == collection["another_intfield"]

    example8 = create_thing_without_server(Example8)
    bound_collection = example8.base_descriptors
    assert bound_collection.is_bound is True
    bound_names = list(bound_collection)
    assert set(bound_names) == {"intfield", "strprop", "another_intfield"}
    assert len(bound_collection) == 3

    bound_intfield_info = bound_collection["intfield"]
    assert bound_intfield_info.is_bound is True

    assert bound_collection["intfield"] != collection["intfield"]

    assert "spurious_name" not in collection
    assert "spurious_name" not in bound_collection
    assert "spurious_name" not in field_typed_collection
