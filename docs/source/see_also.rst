See Also
========

LabThings-FastAPI makes quite heavy use of a few key concepts from external libraries, including `fastapi`, `pydantic`, and of course Python's core library. This page attempts to summarise these, and also acts as a useful place for docstrings to link to, so we can avoid repetition.

.. _descriptors:

Descriptors
-----------

Descriptors are a way to itercept attribute access on an object. By default, attributes of an object are just variables - so an object called ``foo`` might have an attribute called ``bar``, and you may read its value with ``foo.bar``, write its value with ``foo.bar = "baz"``, and delete the attribute with ``del foo.bar``. If ``foo`` is a descriptor, Python will call the ``__get__`` method of that descriptor when it's read and the ``__set__`` method when it's written to. You have quite probably used a descriptor already, because the built-in `~builtins.property` creates a descriptor object: that's what runs your getter method when the property is accessed. The descriptor protocol is described with plenty of examples in the `Descriptor Guide`_ in the Python documentation.

In LabThings-FastAPI, descriptors are used to implement :ref:`wot_actions` and :ref:`wot_properties` on `.Thing` subclasses. The intention is that these will function like standard Python methods and properties, but will also be available over HTTP, along with automatic documentation in the :ref:`wot_td` and OpenAPI documents.

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

* Descriptor objects **may know their name**. Python calls ``__set_name__`` on a descriptor if it is available. This allows the descriptor to know the name of the attribute to which it is assigned. LabThings-FastAPI uses the name in the URL and in the Thing Description. When ``__set_name__`` is called, the descriptor **is also passed the class that owns it**. This allows us to check for type hints and docstrings that are part of the class, rather than part of the descriptor.
* There is a convention that descriptors return their value when accessed as an instance attribute, but return themselves when accessed as a class attribute (as done by `builtins.property`). LabThings adheres to that convention.

.. _`Descriptor Guide`: https://docs.python.org/3/howto/descriptor.html