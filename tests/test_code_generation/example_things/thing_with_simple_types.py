"""An example Thing to make a client for.

This tests out various simple datatypes, and different
combinations of types/return values for actions.
"""

from typing import Any

import labthings_fastapi as lt


class SimpleTypeThing(lt.Thing):
    """A Thing that covers all the branches of code generation.

    Note that this isn't exhaustive with respect to datatypes: wider
    coverage of types should happen in the round-trip test of
    `DataSchemaConverter.convert`.
    """

    strprop: str = lt.property(default="")
    """A description of strprop."""

    intprop: int = lt.property(default=0)
    floatprop: float = lt.property(default=0)
    boolprop: bool = lt.property(default=False)
    anyprop: Any = lt.property(default=None)

    optionalint: int | None = lt.property(default=None)
    """This property should be `Union[int, None]`."""

    tupleprop: tuple[int, str] = lt.property(default=(0, "hello"))

    rolistprop: list[int] = lt.property(default_factory=list, readonly=True)
    """This property should show up read-only."""

    @lt.action
    def no_args_no_return(self) -> None:
        """Do something that has no input or output."""
        pass

    @lt.action
    def with_args_return_int(self, a: int, b: str | None = None) -> int:
        """This action has arguments and a return type."""
        return 42

    @lt.action
    def no_type_hints(self, a, b=None):
        """Everything should be typed Any."""
        return "Forty Two."
