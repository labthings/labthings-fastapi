Quick start
===========

The fastest way to get started with `labthings-fastapi` is to try out one of the examples.

You can install `labthings-fastapi` using `pip`:

.. code-block:: bash

    pip install labthings-fastapi

Then, paste the following into a python file, ``counter.py``:

.. code-block:: python
    
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

You can then run this file with `uvicorn`:

.. code-block:: bash

    uvicorn counter:app --reload

This will start a server on `http://localhost:8000` that serves the `TestThing` thing. Visiting `http://localhost:8000/test/` will show the thing description, and you can interact with the actions and properties using the Swagger UI at `http://localhost:8000/docs/`.
