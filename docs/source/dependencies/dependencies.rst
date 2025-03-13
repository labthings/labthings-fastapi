
Dependencies
============

Simple actions depend only on their input parameters and the :class:`~labthings_fastapi.thing.Thing` on which they are defined. However, it's quite common to need something else, for example accessing another :class:`~labthings_fastapi.thing.Thing` instance on the same LabThings server. There are two important principles to bear in mind here:

* Other :class:`~labthings_fastapi.thing.Thing` instances should be accessed using a :class:`~labthings_fastapi.client.in_server.DirectThingClient` subclass if possible. This creates a wrapper object that should work like a :class:`~labthings_fastapi.client.ThingClient`, meaning your code should work either on the server or in a client script. This makes the code much easier to debug.
* LabThings uses the FastAPI "dependency injection" mechanism, where you specify what's needed with type hints, and the argument is supplied automatically at run-time. You can see the `FastAPI documentation`_ for more information.

LabThings provides a shortcut to create the annotated type needed to declare a dependency on another :class:`~labthings_fastapi.thing.Thing`, with the function :func:`~labthings_fastapi.dependencies.thing.direct_thing_client_dependency`. This generates a type annotation that you can use when you define your actions, that will supply a client object when the action is called. 

:func:`~labthings_fastapi.dependencies.thing.direct_thing_client_dependency` takes a :func:`~labthings_fastapi.thing.Thing` class and a path as arguments: these should match the configuration of your LabThings server. Optionally, you can specify the actions that you're going to use. The default behaviour is to make all actions available, however it is more efficient to specify only the actions you will use.

Dependencies are added recursively - so if you depend on another Thing, and some of its actions have their own dependencies, those dependencies are also added to your action. Using the ``actions`` argument means you only need the dependencies of the actions you are going to use, which is more efficient.

.. literalinclude:: example.py
    :language: python
    
In the example above, the :func:`increment_counter` action on :class:`TestThing` takes a :class:`MyThing` as an argument. When the action is called, the ``my_thing`` argument is supplied automatically. The argument is not the :class:`MyThing` instance, instead it is a wrapper class (a dynamically generated :class:`~labthings_fastapi.client.in_server.DirectThingClient` subclass). The wrapper should have the same signature as a :class:`~labthings_fastapi.client.ThingClient`. This means any dependencies of actions on the :class:`MyThing` are automatically supplied, so you only need to worry about the arguments that are not dependencies. The aim of this is to ensure that the code you write for your :class:`Thing` is as similar as possible to the code you'd write if you were using it through the Python client module.

If you need access to the actual Python object (e.g. you need to access methods that are not decorated as actions), you can use the :func:`~labthings_fastapi.dependencies.raw_thing.raw_thing_dependency` function instead. This will give you the actual Python object, but you will need to supply all the arguments of the actions, including dependencies, yourself.

.. _`FastAPI documentation`: https://fastapi.tiangolo.com/tutorial/dependencies/