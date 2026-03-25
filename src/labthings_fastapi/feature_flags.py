"""Control of optional features in LabThings.

This module provides a way to globally enable or disable certain features of LabThings.
When a new, non-backwards-compatible feature is added, it will usually be disabled by
default. This module provides an object `.FEATURE_FLAGS` that allows control over
optional features.

The default values of `.FEATURE_FLAGS` may change with new LabThings releases. The usual
sequence of events would be that a new feature is added (disabled by default), then the
feature flag is enabled by default in a subsequent release. If the intention is that the
feature will become non-optional, disabling the feature will raise a
`DeprecationWarning` for at least one release cycle before it is removed.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any


@dataclass
class LabThingsFeatureFlags:
    """Control over optional features of LabThings."""

    validate_properties_on_set: bool = False
    """Whether validation logic runs when properties are set in Python."""

    @contextmanager
    def set_temporarily(
        self,
        **kwargs: Any,
    ) -> Iterator[None]:
        r"""Temporarily set feature flags in a context manager.

        This function may be used in a `with:` block to set feature flags and
        then reset them afterwards. This is primarily useful for testing.

        :param \**kwargs: the feature flags to set for the duration of the ``with:``
            block. The argument names must match attributes of this object.

        .. code-block: python

           with FEATURE_FLAGS.set_temporarily(validate_properties_on_set=True):
               my_thing.positive_int = -10  # Raises an exception

        """
        values_before = {k: getattr(self, k) for k in kwargs.keys()}
        try:
            for k, v in kwargs.items():
                setattr(self, k, v)
            yield
        finally:
            for k, v in values_before.items():
                setattr(self, k, v)


FEATURE_FLAGS = LabThingsFeatureFlags()
r"""This module-level object allows features of LabThings to be controlled.

See the documentation for the class `.LabThingsFeatureFlags` for details of the
flags and what they do. More information is available in :ref:`optional_features`\ .
"""
