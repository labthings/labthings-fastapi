.. _tutorial_properties:
.. _properties:

Properties
=========================



Properties are values that can be read from and written to a Thing. They are used to represent the state of the Thing, such as its current temperature, brightness, or status. :ref:`wot_properties` are a key concept in the Web of Things standard.

LabThings implements properties in a very similar way to the built-in Python `~builtins.property`. The key difference is that defining an attribute as a `.property` means that the property will be listed in the :ref:`gen_td` and exposed over HTTP. This is important for two reasons:

* Only properties declared using `.property` (usually imported as ``lt.property``) can be accessed over HTTP. Regular attributes or properties using `builtins.property` are only available to your `.Thing` internally, except in some special cases.
* Communication between `.Thing`\ s within a LabThings server should be done using a `.DirectThingClient` class. The purpose of `.DirectThingClient` is to provide the same interface as a `.ThingClient` over HTTP, so it will also only expose functionality described in the Thing Description.

You can add properties to a `.Thing` by using `.property` (usually imported as ``lt.property``).

Data properties
-------------------------

Data properties behave like variables: they simply store a value that is used by other code on the `.Thing`. They are defined similarly to fields in `dataclasses` or `pydantic` models:

.. code-block:: python

    import labthings_fastapi as lt

    class MyThing(lt.Thing):
        my_property: int = lt.property(default=42)

The example above defines a property called `my_property` that has a default value of `42`. Note the type hint `int` which indicates that the property should hold an integer value. This is important, as the type will be enforced when the property is written to via HTTP, and it will appear in :ref:`gen_docs`. By default, this property may be read or written to by HTTP requests. If you want to make it read-only, you can set the `readonly` parameter to `True`:

.. code-block:: python

    class MyThing(lt.Thing):
        my_property: int = lt.property(default=42, readonly=True)

Note that the ``readonly`` parameter only affects *client* code, i.e. it may not be written to via HTTP requests or `.DirectThingClient` instances. However, the property can still be modified by the Thing's code, e.g. in response to an action or another property change as ``self.my_property = 100``.

It is a good idea to make sure there is a docstring for your property. This will be used in the :ref:`gen_docs`, and it will help users understand what the property is for. You can add a docstring to the property by placing a string immediately after the property definition:

.. code-block:: python

    class MyThing(lt.Thing):
        my_property: int = lt.property(default=42, readonly=True)
        """A property that holds an integer value."""

You don't need to include the type in the docstring, as it will be inferred from the type hint. However, you can include additional information about the property, such as its units or any constraints on its value.

Data properties may be *observed*, which means notifications will be sent when the property is written to (see below).

Functional properties
-------------------------

It is also possible to have properties that run code when they are read or written to. These are called functional properties, and they are defined using the `lt.FunctionalProperty` class. They might communicate with hardware (for example to read or write a setting on an instrument), or they might perform some computation based on other properties. They are defined with a decorator, very similarly to the  built-in `property` function:

.. code-block:: python

    import labthings_fastapi as lt

    class MyThing(lt.Thing):
        my_property: int = lt.property(default=42)
        """A property that holds an integer value."""

        @lt.property
        def twice_my_property(self) -> int:
            """Twice the value of my_property."""
            return self.my_property * 2

The example above defines a functional property called `twice_my_property` that returns twice the value of `my_property`. The type hint `-> int` indicates that the property should return an integer value. When this property is read via HTTP, the code in the method will be executed, and the result will be returned to the client. As with `property`, the docstring of the property is taken from the method's docstring, so you can include additional information about the property there.

Functional properties may also have a "setter" method, which is called when the property is written to via HTTP. This allows you to perform some action when the property is set, such as updating a hardware setting or performing some computation. The setter method should take a single argument, which is the new value of the property:

.. code-block:: python

    import labthings_fastapi as lt

    class MyThing(lt.Thing):
        my_property: int = lt.property(default=42)
        """A property that holds an integer value."""

        @lt.property
        def twice_my_property(self) -> int:
            """Twice the value of my_property."""
            return self.my_property * 2

        @twice_my_property.setter
        def twice_my_property(self, value: int):
            """Set the value of twice_my_property."""
            self.my_property = value // 2

Adding a setter makes the property read-write (if only a getter is present, it must be read-only). 

It is possible to make a property read-only for clients by setting its ``readonly`` attribute: this has the same behaviour as for data properties.

.. code-block:: python

    import labthings_fastapi as lt

    class MyThing(lt.Thing):
        my_property: int = lt.property(default=42)
        """A property that holds an integer value."""

        @lt.property
        def twice_my_property(self) -> int:
            """Twice the value of my_property."""
            return self.my_property * 2

        @twice_my_property.setter
        def twice_my_property(self, value: int):
            """Set the value of twice_my_property."""
            self.my_property = value // 2

        # Make the property read-only for clients
        twice_my_property.readonly = True

In the example above, ``twice_my_property`` may be set by code within ``MyThing`` but cannot be written to via HTTP requests or `.DirectThingClient` instances.

Functional properties may not be observed, as they are not backed by a simple value. If you need to notify clients when the value changes, you can use a data property that is updated by the functional property. In the example above, ``my_property`` may be observed, while ``twice_my_property`` cannot be observed. It would be possible to observe changes in ``my_property`` and then query ``twice_my_property`` for its new value.

HTTP interface
--------------

LabThings is primarily controlled using HTTP. Mozilla have a good `Overview of HTTP`_ that is worth a read if you are unfamiliar with the concept of requests, or what ``GET`` and ``PUT`` mean.

Each property in LabThings will be assigned a URL, which allows it to be read and (optionally) written to. The easiest way to explore this is in the interactive OpenAPI documentation, served by your LabThings server at ``/docs``\ . Properties can be read using a ``GET`` request and written using a ``PUT`` request.

LabThings follows the `HTTP Protocol Binding`_ from the Web of Things standard. That's quite a detailed document: for a gentle introduction to HTTP and what a request means, see 

.. _`Overview of HTTP`: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Overview
.. _`HTTP Protocol Binding`: https://w3c.github.io/wot-binding-templates/bindings/protocols/http/index.html

Observable properties
-------------------------

Properties can be made observable, which means that clients can subscribe to changes in the property's value. This is useful for properties that change frequently, such as sensor readings or instrument settings. In order for a property to be observable, LabThings must know whenever it changes. Currently, this means only data properties can be observed, as functional properties do not have a simple value that can be tracked.

Properties are currently only observable via websockets: in the future, it may be possible to observe them from other `.Thing` instances or from other parts of the code.

.. _settings:

Settings
------------

Settings are properties with an additional feature: they are saved to disk. This means that settings will be automatically restored after the server is restarted. The function `.setting` can be used to declare a `.DataSetting` or decorate a function to make a `.FunctionalSetting` in the same way that `.property` can. It is usually imported as ``lt.setting``\ .
