.. tutorial_thing:

Writing a Thing
=========================

In this section, we will write a simple example `.Thing` that provides some functionality on the server. 

.. note::
    
    Usually, you will write your own `.Thing` in a separate Python module and run it using a configuration file as described in :ref:`tutorial_running`. However, for this tutorial, we will write the `.Thing` in a single file, and use a ``__name__ == "__main__"`` block to run it directly. This is not recommended for production code, but it is convenient for a tutorial.

Our first Thing will pretend to be a light: we can set its brightness and turn it on and off. A first, most basic implementation might look like:

.. code-block:: python

    import labthings_fastapi as lt

    class Light(lt.Thing):
        """A computer-controlled light, our first example Thing."""

        brightness: int = lt.property(default=100)
        """The brightness of the light, in % of maximum."""

        is_on: bool = lt.property(default=False, readonly=true)
        """Whether the light is currently on."""

        @lt.action
        def toggle(self):
            """Swap the light between on and off."""
            self.is_on = not self.is_on

    
    server = lt.ThingServer()
    server.add_thing("light", Light)

    if __name__ == "__main__":
        import uvicorn
        # We run the server using `uvicorn`:
        uvicorn.run(server.app, port=5000)

If you visit `http://localhost:5000/light`, you will see the Thing Description. You can also interact with it using the OpenAPI documentation at `http://localhost:5000/docs`. If you visit `http://localhost:5000/light/brightness`, you can set the brightness of the light, and if you visit `http://localhost:5000/light/is_on`, you can see whether the light is on. Changing values on the server requires a ``PUT`` or ``POST`` request, which is easiest to do using the OpenAPI "Try it out" feature. Check that you can use a ``POST`` request to the ``toggle`` endpoint to turn the light on and off.

There are two types of :ref:`wot_affordances` in this example: properties and actions. Properties are used to read and write values, while actions are used to perform operations that change the state of the Thing. In this case, we have a property for the brightness of the light and a property to indicate whether the light is on or off. The action ``toggle`` changes the state of the light by toggling the ``is_on`` property between ``True`` and ``False``.