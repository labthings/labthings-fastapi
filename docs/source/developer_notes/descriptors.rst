.. _descriptors:

Descriptors
===========

Descriptors are a way to intercept attribute access on an object, and they are used extensively by LabThings to add functionality to `.Thing` instances, while continuing to look like normal Python objects.

By default, attributes of an object are just variables - so an object called ``foo`` might have an attribute called ``bar``, and you may read its value with ``foo.bar``, write its value with ``foo.bar = "baz"``, and delete the attribute with ``del foo.bar``. If ``foo`` is a descriptor, Python will call the ``__get__`` method of that descriptor when it's read and the ``__set__`` method when it's written to. You have quite probably used a descriptor already, because the built-in `~builtins.property` creates a descriptor object: that's what runs your getter method when the property is accessed. The descriptor protocol is described with plenty of examples in the `Descriptor Guide`_ in the Python documentation.

In LabThings-FastAPI, descriptors are used to implement :ref:`actions` and :ref:`properties` on `.Thing` subclasses. The intention is that these will function like standard Python methods and properties, but will also be available over HTTP, along with :ref:`gen_docs`.

.. _field_typing:

Field typing
------------

:ref:`properties` and :ref:`settings` in LabThings-FastAPI are implemented using descriptors. The type of these descriptors is usually determined from the type hint on the class attribute to which they are assigned. For example:

.. code-block:: python

    class MyThing(lt.Thing):
        my_property: int = lt.property(default=0)
        """An integer property."""

This makes it clear to anyone using ``MyThing`` that ``my_property`` is an integer, and should be picked up by most type checking/autocompletion tools. However, because the annotation is attached to the *class* and not passed to the underlying `.DataProperty` descriptor, we need to use the descriptor protocol to figure it out.

Field typing in LabThings is implemented by `.FieldTypedBaseDescriptor` and there are docstrings on all of the relevant "magic" methods explaining what each one does. Below, there is a brief overview of how these fit together.

* When the descriptor is created, we don't know its name or type. ``__init__`` just stores any parameters that were passed to the descriptor constructor (e.g. ``default``). Some subclasses (in particular `.FunctionalProperty`) may be able to determine the type at this point, in which case it can be assigned to ``self._value_type``, and no errors will be raised in ``__set_name__`` if there is no type hint on the attribute.
* When the class is created, Python calls the ``__set_name__`` method of the descriptor, passing in the owning class and the descriptor's name. This allows the descriptor to check whether there is a type annotation, but we don't evaluate it yet. Type annotations are deliberately not evaluated until they are needed, to allow forward references to work as intended. If there isn't a type hint, and the type hasn't been specified in some other way, we raise an exception at this point. This will appear to come from the end of the class definition, because `__set_name__` is called after all the class attributes have been created. The exception should contain the name of the attribute that's missing a type hint (and this is tested in our test suite).
* The first time `.FieldTypedBaseDescriptor.value_type` is accessed, we evaluate the type hint (if any) using `typing.get_type_hints`. This allows forward references to be resolved correctly. The evaluated type is cached so that subsequent accesses are fast.
* The ``__get__`` and ``__set__`` methods get and set the value of the property. Currently, no run-time type checking is done if the attribute is used from Python. The type hint is used when generating the :ref:`gen_td` and OpenAPI documentation, and is used to validate values that are set over HTTP.

.. _descriptor_implementation:

Descriptor implementation
-------------------------

There are a few useful notes that relate to many of the descriptors in LabThings-FastAPI:

* Descriptor objects **may have more than one owner**. As a rule, a descriptor object
    (e.g. an instance of `.DataProperty`) is assigned to an attribute of one `.Thing` subclass. There may, however, be multiple *instances* of that class, so it is not safe to assume that the descriptor object corresponds to only one `.Thing`. This is why the `.Thing` is passed to the ``__get__`` method: we should ensure that any values being remembered are keyed to the owning `.Thing` and are not simply stored in the descriptor. Usually, this is done using `.WeakKeyDictionary` objects, which allow us to look up values based on the `.Thing`, without interfering with garbage collection.

    The example below shows how this can go wrong.

    .. code-block:: python

        class BadProperty:
            "An example of a descriptor that has unwanted behaviour."
            def __init__(self):
                self._value = None
            
            def __get__(self, obj):
                return self._value

            def __set__(self, obj, val):
                self._value = val

        class BrokenExample:
            myprop = BadProperty()

        a = BrokenExample()
        b = BrokenExample()

        assert a.myprop is None
        b.myprop = True
        assert a.myprop is None  # FAILS because `myprop` shares values between a and b

* Descriptor objects **may know their name**. Python calls ``__set_name__`` on a descriptor if it is available. This allows the descriptor to know the name of the attribute to which it is assigned. LabThings-FastAPI uses the name in the URL and in the Thing Description. When ``__set_name__`` is called, the descriptor can also access the class that owns it, which we use to implement :ref:`field_typing` above.
* There is a convention that descriptors return their value when accessed as an instance attribute, but return themselves when accessed as a class attribute (as done by `builtins.property`). All descriptors that inherit from `.BaseDescriptor` adhere to that convention.

.. _`Descriptor Guide`: https://docs.python.org/3/howto/descriptor.html