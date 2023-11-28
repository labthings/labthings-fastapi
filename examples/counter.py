import time
from labthings_fastapi.thing import Thing
from labthings_fastapi.decorators import thing_action
from labthings_fastapi.descriptors import PropertyDescriptor
from labthings_fastapi.thing_server import ThingServer


class TestThing(Thing):
    """A test thing with a counter property and a couple of actions"""

    @thing_action
    def increment_counter(self) -> None:
        """Increment the counter property

        This action doesn't do very much - all it does, in fact,
        is increment the counter (which may be read using the
        `counter` property).
        """
        self.counter += 1

    @thing_action
    def slowly_increase_counter(self) -> None:
        """Increment the counter slowly over a minute"""
        for i in range(60):
            time.sleep(1)
            self.increment_counter()

    counter = PropertyDescriptor(
        model=int, initial_value=0, readonly=True, description="A pointless counter"
    )


server = ThingServer()
server.add_thing(TestThing(), "/test")
