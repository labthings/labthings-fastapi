"""
Example Thing subclasses, used for testing and demonstration purposes.
"""

import time
from typing import Optional, Annotated
from labthings_fastapi.thing import Thing
from labthings_fastapi.decorators import thing_action, thing_property
from labthings_fastapi.descriptors import PropertyDescriptor
from pydantic import Field


class MyThing(Thing):
    """An example Thing with a few affordances"""

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
        """Quite a complicated action

        This action has lots of parameters and is designed to confuse my schema
        generator. I hope it doesn't!

        I might even use some Markdown here:

        * If this renders, it supports lists
        * With at east two items.
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
        """An action that returns a dict"""
        out: dict[str, Optional[str]] = {"key": "value"}
        if extra_key is not None:
            out[extra_key] = extra_value
        return out

    @thing_action
    def increment_counter(self):
        """Increment the counter property

        This action doesn't do very much - all it does, in fact,
        is increment the counter (which may be read using the
        `counter` property).
        """
        self.counter += 1

    @thing_action
    def slowly_increase_counter(self, increments: int = 60, delay: float = 1):
        """Increment the counter slowly over a minute"""
        for i in range(increments):
            time.sleep(delay)
            self.increment_counter()

    counter = PropertyDescriptor(
        model=int, initial_value=0, readonly=True, description="A pointless counter"
    )

    foo = PropertyDescriptor(
        model=str,
        initial_value="Example",
        description="A pointless string for demo purposes.",
    )

    @thing_action
    def action_without_arguments(self) -> None:
        """An action that takes no arguments"""
        pass

    @thing_action
    def action_with_only_kwargs(self, **kwargs) -> None:
        """An action that takes **kwargs"""
        pass


class ThingWithBrokenAffordances(Thing):
    """A Thing that raises exceptions in actions/properites"""

    @thing_action
    def broken_action(self):
        """An action that raises an exception"""
        raise RuntimeError("This is a broken action")

    @thing_property
    def broken_property(self):
        """A property that raises an exception"""
        raise RuntimeError("This is a broken property")


class ThingThatCantInstantiate(Thing):
    """A Thing that raises an exception in __init__"""

    def __init__(self):
        raise RuntimeError("This thing can't be instantiated")


class ThingThatCantStart(Thing):
    """A Thing that raises an exception in __enter__"""

    def __enter__(self):
        raise RuntimeError("This thing can't start")

    def __exit__(self, exc_t, exc_v, exc_tb):
        pass
