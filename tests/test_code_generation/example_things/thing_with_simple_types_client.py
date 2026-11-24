"""A client for the SimpleTypeThing Thing."""

from typing import Any, Union

from labthings_fastapi.client import ThingClient, client_property


class SimpleTypeThingClient(ThingClient):
    """A Thing that covers all the branches of code generation.

    Note that this isn't exhaustive with respect to datatypes: wider
    coverage of types should happen in the round-trip test of
    `DataSchemaConverter.convert`.
    """

    anyprop: Any = client_property(read_only=False, write_only=False)
    "anyprop"
    boolprop: bool = client_property(read_only=False, write_only=False)
    "boolprop"
    floatprop: float = client_property(read_only=False, write_only=False)
    "floatprop"
    intprop: int = client_property(read_only=False, write_only=False)
    "intprop"
    optionalint: Union[int, None] = client_property(read_only=False, write_only=False)
    "This property should be `Union[int, None]`."
    rolistprop: list[int] = client_property(read_only=True, write_only=False)
    "This property should show up read-only."
    strprop: str = client_property(read_only=False, write_only=False)
    "A description of strprop."
    tupleprop: tuple[int, str] = client_property(read_only=False, write_only=False)
    "tupleprop"

    def no_args_no_return(self, **kwargs: Any) -> None:
        """Do something that has no input or output."""
        return self.invoke_action("no_args_no_return", **kwargs)

    def no_type_hints(self, /, *, a: Any, b: Any = ..., **kwargs: Any) -> Any:
        """Everything should be typed Any."""
        return self.invoke_action("no_type_hints", a=a, b=b, **kwargs)

    def with_args_return_int(
        self, /, *, a: int, b: Union[str, None] = ..., **kwargs: Any
    ) -> int:
        """This action has arguments and a return type."""
        return self.invoke_action("with_args_return_int", a=a, b=b, **kwargs)
