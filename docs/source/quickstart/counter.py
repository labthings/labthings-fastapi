"""An example Thing that implements a counter."""

import time
import labthings_fastapi as lt


class TestThing(lt.Thing):
    """A test thing with a counter property and a couple of actions."""

    @lt.thing_action
    def increment_counter(self) -> None:
        """Increment the counter property.

        This action doesn't do very much - all it does, in fact,
        is increment the counter (which may be read using the
        `counter` property).
        """
        self.counter += 1

    @lt.thing_action
    def slowly_increase_counter(self) -> None:
        """Increment the counter slowly over a minute."""
        for _i in range(60):
            time.sleep(1)
            self.increment_counter()

    counter: int = lt.property(default=0, readonly=True)
    "A pointless counter."


if __name__ == "__main__":
    import uvicorn

    server = lt.ThingServer()

    # The line below creates a TestThing instance and adds it to the server
    server.add_thing("counter", TestThing)

    # We run the server using `uvicorn`:
    uvicorn.run(server.app, port=5000)
