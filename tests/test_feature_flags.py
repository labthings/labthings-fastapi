"""Test the feature flags mechanism.

Specific feature flags should be tested by the test code for the relevant feature. This
test module checks that `set_temporarily` works as expected.
"""

import pytest

import labthings_fastapi as lt


@pytest.mark.parametrize("value", [True, False])
def test_set_temporarily(value):
    """Test values may be set and reset."""
    value_before = lt.FEATURE_FLAGS.validate_properties_on_set

    with lt.FEATURE_FLAGS.set_temporarily(validate_properties_on_set=value):
        assert lt.FEATURE_FLAGS.validate_properties_on_set == value

        with lt.FEATURE_FLAGS.set_temporarily(validate_properties_on_set=not value):
            assert lt.FEATURE_FLAGS.validate_properties_on_set != value

        assert lt.FEATURE_FLAGS.validate_properties_on_set == value

    assert lt.FEATURE_FLAGS.validate_properties_on_set == value_before


def test_set_bad_setting():
    """Test for errors when bad flags are used."""
    with pytest.raises(AttributeError):
        with lt.FEATURE_FLAGS.set_temporarily(bogus_name=True):
            pass
    with pytest.raises(AttributeError):
        lt.FEATURE_FLAGS.bogus_name = True
