"""Example Thing subclasses, used for testing and demonstration purposes.

Most of these are broken in some way and used for testing. These should be
moved into the unit tests.
"""

import time
from typing import Any, Optional, Annotated
from labthings_fastapi.thing import Thing
from labthings_fastapi.decorators import thing_action
from labthings_fastapi.properties import property as lt_property
from pydantic import Field


class MyThing(Thing):
    """An example Thing with a few affordances."""

    @thing_action
    def anaction(
        self,
        repeats: Annotated[
            int, Field(description="The number of times to try the action")
        ],  # no default = required parameter
        undocumented: int,
        title: Annotated[
            str, Field(description="the title of the invocation")
        ] = "Untitled",
        attempts: Annotated[
            Optional[list[str]],
            Field(
                description="Names for each attempt - I suggest final, Final, FINAL."
            ),
        ] = None,
    ) -> dict[str, str]:
        """Quite a complicated action.

        This action has lots of parameters and is designed to confuse my schema
        generator. I hope it doesn't!

        I might even use some Markdown here:

        * If this renders, it supports lists
        * With at least two items.

        There is also a parameter and return block to satisfy docstring validators.
        This may be preferable to annotations on the arguments.

        :param repeats: How many times to do it.
        :param undocumented: There's no description on this field's type hint.
        :param title: A human-readable title.
        :param attempts: A list of names of attempts.

        :return: A dictionary with strings as keys and values.
        """
        # We should be able to call actions as normal Python functions
        self.increment_counter()
        return {"end_result": "finished!!"}

    @thing_action
    def make_a_dict(
        self,
        extra_key: Optional[str] = None,
        extra_value: Optional[str] = None,
    ) -> dict[str, Optional[str]]:
        """Do something that returns a dict.

        :param extra_key: An additional key.
        :param extra_value: An additional value.
        :return: a dictionary.
        """
        out: dict[str, Optional[str]] = {"key": "value"}
        if extra_key is not None:
            out[extra_key] = extra_value
        return out

    @thing_action
    def increment_counter(self) -> None:
        """Increment the counter property.

        This action doesn't do very much - all it does, in fact,
        is increment the counter (which may be read using the
        `counter` property).
        """
        self.counter += 1

    @thing_action
    def slowly_increase_counter(self, increments: int = 60, delay: float = 1) -> None:
        """Increment the counter slowly over a minute.

        :param increments: how many times to increment.
        :param delay: the wait time between increments.
        """
        for _i in range(increments):
            time.sleep(delay)
            self.increment_counter()

    counter: int = lt_property(default=0, readonly=True)
    "A pointless counter"

    foo: str = lt_property(default="Example")
    "A pointless string for demo purposes."

    @thing_action
    def action_without_arguments(self) -> None:
        """Do something that takes no arguments."""
        pass

    @thing_action
    def action_with_only_kwargs(self, **kwargs: dict) -> None:
        r"""Do something that takes \**kwargs.

        :param \**kwargs: Keyword arguments.
        """
        pass


class ThingWithBrokenAffordances(Thing):
    """A Thing that raises exceptions in actions/properties."""

    @thing_action
    def broken_action(self) -> None:
        """Do something that raises an exception.

        :raise RuntimeError: every time.
        """
        raise RuntimeError("This is a broken action")

    @lt_property
    def broken_property(self) -> None:
        """Raise an exception when the property is accessed.

        :raise RuntimeError: every time.
        """
        raise RuntimeError("This is a broken property")


class ThingThatCantInstantiate(Thing):
    """A Thing that raises an exception in __init__."""

    def __init__(self) -> None:
        """Fail to initialise.

        :raise RuntimeError: every time.
        """
        raise RuntimeError("This thing can't be instantiated")


class ThingThatCantStart(Thing):
    """A Thing that raises an exception in __enter__."""

    def __enter__(self) -> None:
        """Fail to start the thing.

        :raise RuntimeError: every time.
        """
        raise RuntimeError("This thing can't start")

    def __exit__(self, exc_t: Any, exc_v: Any, exc_tb: Any) -> None:
        """Don't leave the thing as we never entered.

        :param exc_t: Exception type.
        :param exc_v: Exception value.
        :param exc_tb: Traceback.
        """
        pass
