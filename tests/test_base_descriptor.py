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


def test_docstrings_are_retrieved():
    """Check that the docstring can be picked up from the class definition."""
    docs = get_class_attribute_docstrings(Example)
    assert docs["my_constant"] == "A number that is all mine."
    assert docs["my_property"] == "Docs for my_property."


def test_docstrings_are_cached():
    """Check that the docstrings aren't being regenerated every time."""
    docs1 = get_class_attribute_docstrings(Example)
    docs2 = get_class_attribute_docstrings(Example)
    assert docs1 is docs2


def test_basedescriptor_with_good_docstring():
    """Check we get the right documentation properties."""
    prop = Example.my_property_with_nice_docs
    assert prop.name == "my_property_with_nice_docs"
    assert prop.title == "Title goes here."
    assert prop.description.startswith("The docstring")


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
    e = Example()
    assert e.my_property == "An example value."
