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

from .exceptions import DefaultWillChangeWarning

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


with warnings.catch_warnings():
    # Pydantic will warn that it doesn't enforce the ReadOnly type hint.
    # That's fine: it should help mypy and we don't need to worry that pydantic
    # doesn't enforce it.
    warnings.filterwarnings(
        "ignore",
        ".*Pydantic will not protect items from any mutation on dictionary instances.",
    )
    SETTINGS_TYPEADAPTER = TypeAdapter(ThingClassSettings)


def validate_thing_class_settings(cls: "type[Thing]") -> None:
    """Validate a class settings dict.

    This retrieves the dict from the class, and ensures the attribute
    is a valid `ThingClassSettings` typed dict.

    :param cls: The `Thing` subclass where we are validating.
    :raises InvalidClassSettingsError: if the dictionary is not valid.
    """
    unvalidated = get_class_settings(cls)
    try:
        cls._class_settings = SETTINGS_TYPEADAPTER.validate_python(unvalidated)
    except ValueError as e:
        msg = f"`{cls.__module__}.{cls.__name__}._class_settings` is not valid."
        raise InvalidClassSettingsError(msg) from e

    # Add deprecation warnings here if settings will be removed in the future.


def get_class_settings(cls: "type[Thing]") -> ThingClassSettings:
    """Retrieve a class settings dict or default to an empty dict.

    :param cls: The class from which to retrieve the dict.
    :return: The ``_class_settings`` dict, or an empty dict.
    :raises TypeError: if the settings is not a dictionary.
    """
    try:
        if type(cls._class_settings) is not dict:
            raise TypeError("`_class_settings` must be a `dict`.")
        return cls._class_settings
    except AttributeError:
        return {}


def get_validate_properties_on_set(cls: "type[Thing]") -> bool:
    r"""Determine whether properties should perform validation when set from Python.

    .. note::

        Check that the default value defined here matches the docstring for
        `ThingClassSettings`\ .

    :param cls: the `Thing` subclass on which the property is defined.
    :return: whether validation should be performed.
    """
    settings = get_class_settings(cls)
    value = settings.get(
        "validate_properties_on_set",
        False,
    )
    if not value:
        warnings.warn(
            DefaultWillChangeWarning(
                "`get_validate_properties_on_set` will become `True` by default "
                "in the future, and may become the only option. "
                "Set this property to `True` in "
                f"`{cls.__module__}.{cls.__name__}._class_settings` "
                "to eliminate this warning."
            ),
            stacklevel=3,
        )
    return value
