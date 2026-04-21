"""Settings that control how a `lt.Thing` interacts with LabThings.

This module defines the type used by `lt.Thing._class_settings` to control
how it interacts with LabThings. Most of this module is intended for internal
use: the only user-facing item is the type `ThingClassSettings`
"""

from labthings_fastapi.exceptions import InvalidClassSettingsError
from pydantic import with_config, ConfigDict, TypeAdapter
from typing_extensions import TypedDict, ReadOnly
from typing import TYPE_CHECKING
import warnings

if TYPE_CHECKING:
    from .thing import Thing


@with_config(ConfigDict(extra="forbid"))
class ThingClassSettings(TypedDict, total=False):
    r"""Settings that define how a Thing operates."""

    # Default values are defined in getter functions in the `.thing_class_settings`
    # module as well as in docstrings in this type.

    validate_properties_on_set: ReadOnly[bool]
    """Whether property values are validated when set from Python.

    This is not yet enabled by default, but will be in future.
    A `DeprecationWarning` will be raised if it is not set to `True`.
    """


def validate_thing_class_settings(cls: type[Thing]) -> None:
    """Validate a class settings dict.

    This retrieves the dict from the class, and ensures the attribute
    is a valid `ThingClassSettings` typed dict.

    :param cls: The `Thing` subclass where we are validating.
    :raises InvalidClassSettingsError: if the dictionary is not valid.
    """
    unvalidated = getattr(cls, "_class_settings", {})
    adapter = TypeAdapter(ThingClassSettings)
    try:
        cls._class_settings = adapter.validate_python(unvalidated)
    except ValueError as e:
        msg = "The settings dictionary for this class is not valid."
        raise InvalidClassSettingsError(msg) from e

    if not get_validate_properties_on_set(cls):
        warnings.warn(
            DeprecationWarning(
                "`get_validate_properties_on_set will become `True` by default "
                "in the future. Set this property to `True` to eliminate this warning."
            ),
            stacklevel=3,
        )


def get_validate_properties_on_set(cls: type[Thing]) -> bool:
    r"""Determine whether properties should perform validation when set from Python.

    .. note::

        Check that the default value defined here matches the docstring for
        `ThingClassSettings`\ .

    :param cls: the `Thing` subclass on which the property is defined.
    :return: whether validation should be performed.
    """
    return cls._class_settings.get(
        "validate_properties_on_set",
        False,
    )
