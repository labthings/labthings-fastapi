r"""Pydantic models to enable server configuration to be loaded from file.

The models in this module allow `.ThingConfig` dataclasses to be constructed
from dictionaries or JSON files. They also describe the full server configuration
with `.ServerConfigModel`\ . These models are used by the `.cli` module to
start servers based on configuration files or strings.
"""

from pydantic import BaseModel, Field, ImportString, AliasChoices, field_validator
from typing import Any, Annotated, TypeAlias
from collections.abc import Mapping, Sequence, Iterable


class ThingConfig(BaseModel):
    r"""The information needed to add a `.Thing` to a `.ThingServer`\ ."""

    cls: ImportString = Field(
        validation_alias=AliasChoices("cls", "class"),
        description="The Thing subclass to add to the server.",
    )

    args: Sequence[Any] = Field(
        default_factory=list,
        description="Positional arguments to pass to the constructor of `cls`.",
    )

    kwargs: Mapping[str, Any] = Field(
        default_factory=dict,
        description="Keyword arguments to pass to the constructor of `cls`.",
    )

    thing_slots: Mapping[str, str | Iterable[str] | None] = Field(
        default_factory=dict,
        description=(
            """Connections to other Things.

            Keys are the names of attributes of the Thing and the values are
            the name(s) of the Thing(s) you'd like to connect. If this is left
            at its default, the connections will use their default behaviour, usually
            automatically connecting to a Thing of the right type.
            """
        ),
    )


ThingName = Annotated[
    str,
    Field(min_length=1, pattern=r"^([a-zA-Z0-9\-_]+)$"),
]


ThingsConfig: TypeAlias = Mapping[ThingName, ThingConfig | ImportString]


class ThingServerConfig(BaseModel):
    r"""The configuration parameters for a `.ThingServer`\ ."""

    things: ThingsConfig = Field(
        description=(
            """A mapping of names to Thing configurations.

            Each Thing on the server must be given a name, which is the dictionary
            key. The value is either the class to be used, or a `.ThingConfig`
            object specifying the class, initial arguments, and other settings.
            """
        ),
    )

    @field_validator("things", mode="after")
    @classmethod
    def check_things(cls, things: ThingsConfig) -> ThingsConfig:
        """Check that the thing configurations can be normalised.

        It's possible to specify the things as a mapping from names to classes.
        We use `pydantic.ImportString` as the type of the classes: this takes a
        string, and imports the corresponding Python object. When loading config
        from JSON, this does the right thing - but when loading from Python objects
        it will accept any Python object.

        This validator runs `.normalise_thing_config` to check each value is either
        a valid `.ThingConfig` or a type or a mapping. If it's a mapping, we
        will attempt to make a `.ThingConfig` from it. If it's a `type` we will
        create a `.ThingConfig` using that type as the class. We don't check for
        `.Thing` subclasses in this module to avoid a dependency loop.

        :param things: The validated value of the field.

        :return: A copy of the input, with all values converted to `.ThingConfig`
            instances.
        """
        return normalise_things_config(things)

    @property
    def thing_configs(self) -> Mapping[ThingName, ThingConfig]:
        r"""A copy of the ``things`` field where every value is a ``.ThingConfig``\ .

        The field validator on ``things`` already ensures it returns a mapping, but
        it's not typed strictly, to allow Things to be specified with just a class.

        This property returns the list of `.ThingConfig` objects, and is typed strictly.
        """
        return normalise_things_config(self.things)

    settings_folder: str | None = Field(
        default=None,
        description="The location of the settings folder.",
    )


def normalise_things_config(things: ThingsConfig) -> Mapping[ThingName, ThingConfig]:
    r"""Ensure every Thing is defined by a `.ThingConfig` object.

    Things may be specified either using a `.ThingConfig` object, or just a bare
    `.Thing` subclass, if the other parameters are not needed. To simplify code that
    uses the configuration, this function wraps bare classes in a `.ThingConfig` so
    the values are uniformly typed.

    :param things: A mapping of names to Things, either classes or `.ThingConfig`
        objects.

    :return: A mapping of names to `.ThingConfig` objects.

    :raises ValueError: if a Python object is passed that's neither a `type` nor
        a `dict`\ .
    """
    normalised: dict[str, ThingConfig] = {}
    for k, v in things.items():
        if isinstance(v, ThingConfig):
            normalised[k] = v
        elif isinstance(v, Mapping):
            normalised[k] = ThingConfig.model_validate(v)
        elif isinstance(v, type):
            normalised[k] = ThingConfig(cls=v)
        else:
            raise ValueError(
                "Things must be specified either as a class or a ThingConfig."
            )
    return normalised
