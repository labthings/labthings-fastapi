import pytest
from labthings_fastapi.base_descriptor import (
    BaseDescriptor,
    DescriptorNotAddedToClassError,
    get_class_attribute_docstrings,
)


class MockProperty(BaseDescriptor[str]):
    """A mock property class."""

    # The line below isn't defined on a `Thing`, so mypy
    # errors - but we ignore this for testing.
    def instance_get(self, _obj) -> str:  # type: ignore[override]
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
        prop.name


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
        e.base_descriptor
