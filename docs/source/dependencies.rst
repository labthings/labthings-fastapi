
Dependencies
============

Often, a :class:`~labthings_fastapi.thing.Thing` will want to make use of other :class:`~labthings_fastapi.thing.Thing` instances on the server. To make this simple, we use *dependency injection*, which looks at the type hints on your Action's arguments and supplies the appropriate :class:`~labthings_fastapi.thing.Thing` when the action is called. We are piggy-backing on FastAPI's dependency injection mechanism, and you can see the `FastAPI documentation`_ for more information.

The easiest way to access another :class:`~labthings_fastapi.thing.Thing` is using the function :func:`~labthings_fastapi.dependencies.thing.direct_thing_client_dependency`. This generates a type annotation that you can use when you define your actions. Optionally, you can specify the actions that you're going to use - this can be helpful if the thing you're depending on has a lot of actions and you only need a few of them, because all of the dependencies of those actions get added to your action. Most of the time, you can just use the default, which is to include all actions.

.. code-block:: python
    
    from labthings_fastapi.thing import Thing
    from labthings_fastapi.decorators import thing_action
    from labthings_fastapi.dependencies.thing import direct_thing_client_dependency
    from labthings_fastapi.example_thing import MyThing

    MyThingDep = direct_thing_client_dependency(MyThing)

    class TestThing(Thing):
        """A test thing with a counter property and a couple of actions"""

        @thing_action
        def increment_counter(self, my_thing: MyThingDep) -> None:
            """Increment the counter on another thing"""
            my_thing.increment_counter()

In the example above, the :func:`increment_counter` action on :class:`TestThing` takes a :class:`MyThing` as an argument. When the action is called, the :class:`MyThing` instance is passed in as the ``my_thing`` argument. The recipe above doesn't return the `MyThing` instance directly, it returns something that works in a similar way to the Python client. That means any dependencies of actions on the :class:`MyThing` are automatically supplied, so you only need to worry about the arguments you'd supply when calling it over the network. The aim of this is to ensure that the code you write for your :class:`Thing` is as similar as possible to the code you'd write if you were using it through the Python client module.

If you need access to the actual Python object (e.g. you need to access methods that are not decorated as actions), you can use the :func:`~labthings_fastapi.dependencies.raw_thing.raw_thing_dependency` function instead. This will give you the actual Python object, but you will need to manage the dependencies yourself.

.. _`FastAPI documentation`: https://fastapi.tiangolo.com/tutorial/dependencies/