.. _dependencies:

Dependencies
============

.. warning::

    The use of dependencies is now deprecated. See `.thing_connection` and `.ThingServerInterface` for a more intuitive way to access that functionality.

LabThings makes use of the powerful "dependency injection" mechanism in FastAPI. You can see the `FastAPI documentation`_ for more information. In brief, FastAPI dependencies are annotated types that instruct FastAPI to supply certain function arguments automatically. This removes the need to set up resources at the start of a function, and ensures everything the function needs is declared and typed clearly. The most common use for dependencies in LabThings is where an action needs to make use of another `.Thing` on the same `.ThingServer`.

Inter-Thing dependencies
------------------------

.. warning::

    These dependencies are deprecated - see `.thing_connection` instead.

Simple actions depend only on their input parameters and the `.Thing` on which they are defined. However, it's quite common to need something else, for example accessing another `.Thing` instance on the same LabThings server. There are two important principles to bear in mind here:

* Other `.Thing` instances should be accessed using a `.DirectThingClient` subclass if possible. This creates a wrapper object that should work like a `.ThingClient`, meaning your code should work either on the server or in a client script. This makes the code much easier to debug.
* LabThings uses the FastAPI "dependency injection" mechanism, where you specify what's needed with type hints, and the argument is supplied automatically at run-time. You can see the `FastAPI documentation`_ for more information.

In order to use on `.Thing` from another there are three steps, all shown in the example below.

#. Create a `.DirectThingClient` subclass for your target `.Thing`. This can be done using the `.direct_thing_client_class` function, which takes a `.Thing` subclass and a path as arguments: these should match the configuration of your LabThings server.
#. Annotate your client class with `fastapi.Depends()` to mark it as a dependency. You may assign this annotated type to a name, which is much neater when you are using it several times.
#. Use the annotated type as a type hint on one of your action's arguments.

.. literalinclude:: example.py
    :language: python
    
In the example above, the ``increment_counter`` action on ``TestThing`` takes a ``MyThingClient`` as an argument. When the action is called, the ``my_thing`` argument is supplied automatically. The argument is not the ``MyThing`` instance, instead it is a wrapper class ``MyThingClient`` (this is a dynamically generated `.DirectThingClient` subclass). The wrapper should have the same signature as a `.ThingClient` connected to ``MyThing``. This means any dependencies of actions on the ``MyThing`` are automatically supplied, so you only need to worry about the arguments that are not dependencies. The aim of this is to ensure that the code you write for your `.Thing` is as similar as possible to the code you'd write if you were using it through the Python client module.

.. note::

    LabThings provides a shortcut to create the annotated type needed to declare a dependency on another `.Thing`, with the function `.direct_thing_client_dependency`. This generates a type annotation that you can use when you define your actions.
    This shortcut may not work well with type checkers or linters, however, so we now recommend you declare an annotated type instead, as shown in the example.

Dependencies are added recursively - so if you depend on another Thing, and some of its actions have their own dependencies, those dependencies are also added to your action. Using the ``actions`` argument means you only need the dependencies of the actions you are going to use, which is more efficient.

If you need access to the actual Python object (e.g. you need to access methods that are not decorated as actions), you can use the :func:`~labthings_fastapi.dependencies.raw_thing.raw_thing_dependency` function instead. This will give you the actual Python object, but you will need to supply all the arguments of the actions, including dependencies, yourself.

Non-Thing dependencies
----------------------

LabThings provides several other dependencies, which can usually be imported directly as annotated types. For example, if your action needs to display messages as it runs, you may use an `.InvocationLogger`:

.. code-block:: python
    
    import labthings_fastapi as lt

    class NoisyCounter(lt.Thing):
        def count_in_logs(self, logger: lt.deps.InvocationLogger):
            for i in range(10):
                logger.info(f"Counter is now {i}")

Most common dependencies can be found within `labthings_fastapi.deps`.

.. _`FastAPI documentation`: https://fastapi.tiangolo.com/tutorial/dependencies/