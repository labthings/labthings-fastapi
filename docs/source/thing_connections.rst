.. thing_connections:

Thing Connections
=================

It is often desirable for two Things in the same server to be able to communicate.
In order to do this in a nicely typed way that is easy to test and inspect,
LabThings-FastAPI provides `.thing_connection`\ . This allows a `.Thing`
to declare that it depends on another `.Thing` being present, and provides a way for
the server to automatically connect the two when the server is set up.

Thing connections are set up **after** all the `.Thing` instances are initialised.
This means you should not rely on them during initialisation: if you attempt to
access a connection before it is available, it will raise an exception. The
advantage of making connections after initialisation is that we don't need to
worry about the order in which `.Thing`\ s are created.

The following example shows the use of a Thing Connection:

.. code-block:: python

    import labthings_fastapi as lt


    class ThingA(lt.Thing):
        "A class that doesn't do much."

        @lt.action
        def say_hello(self) -> str:
            "A canonical example function."
            return "Hello world."


    class ThingB(lt.Thing):
        "A class that relies on ThingA."

        thing_a: ThingA = lt.thing_connection()

        @lt.action
        def say_hello(self) -> str:
            "I'm too lazy to say hello, ThingA does it for me."
            return self.thing_a.say_hello()


    server = lt.ThingServer()
    server.add_thing("thing_a", ThingA)
    server.add_thing("thing_b", ThingB)


In this example, ``ThingB.thing_a`` is the simplest form of Thing Connection: it
is type hinted as a `.Thing` subclass, and by default the server will look for the
instance of that class and supply it when the server starts. If there is no
matching `.Thing` or if more than one instance is present, the server will fail
to start with a `.ThingConnectionError`\ .

It is also possible to use an optional type hint (``ThingA | None``), which
means there will be no error if a matching `.Thing` instance is not found, and
the connection will evaluate to `None`\ . Finally, a `.thing_connection` may be
type hinted as ``Mapping[str, ThingA]`` which permits zero or more instances to
be connected. The mapping keys are the names of the things.

Configuring Thing Connections
-----------------------------

A Thing Connection may be given a default value. If this is a string, the server
will look up the `.Thing` by name. If the default is `None` the connection will
evaluate to `None` unless explicitly configured.

Connections may also be configured when `.Thing`\ s are added to the server:
`.ThingServer.add_thing` takes an argument that allows connections to be made
by name (or set to `None`). Similarly, if you set up your server using a config
file, each entry in the ``things`` list may have a ``thing_connections`` property
that sets up the connections. To repeat the example above with a configuration
file:

.. code-block:: JSON

    "things": {
        "thing_a": "example:ThingA",
        "thing_b": {
            "class": "example:ThingB",
            "thing_connections": {
                "thing_a": "thing_a"
            }
        }
    }

More detail can be found in the description of `.thing_connection` or the
:mod:`.thing_connections` module documentation.
