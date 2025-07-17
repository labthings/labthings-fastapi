Using Things
============

The interface to a `Thing` is defined by its actions, properties and events [#events]_. These can all be accessed remotely via HTTP from any language, but a more convenient interface in Python is a `.ThingClient` subclass. This provides a simple, pythonic interface to the `.Thing`, allowing you to call actions and access properties as if they were methods and attributes of a Python object.

`.ThingClient` subclasses can be generated dynamically from a URL using :meth:`.ThingClient.from_url`. This creates an object with the right methods, properties and docstrings, though type hints are often missing. The client can be "introspected" to explore its methods and properties using tools that work at run-time (e.g. autocompletion in a Jupyter notebook), but "static" analysis tools will not yet work.

.. [#events] Events are not yet implemented.

Using Things from other languages
----------------------------------

LabThings exposes all the Actions and Properties of each Thing over HTTP, meaning they may be called from nearly every programming language, or interactively using tools such as `curl` or `swagger`. Each Thing is described using both a Thing Description document and an OpenAPI description. Thing Descriptions are a high-level description, standardised by W3C, that can be used to create intuitive client code. There are currently a few tools that work with Thing Description, but the Web of Things standard is still growing and developing. The OpenAPI description is a lower-level description of the HTTP API, which can be used to generate client code in many languages. The OpenAPI description is also used to `render the interactive documentation`_ using Swagger or Redocly, which is available at the `/docs` URL of the server (e.g. `http://localhost:5000/docs` when running a local server).

_`render the interactive documentation`: https://fastapi.tiangolo.com/#interactive-api-docs

Dynamic class generation
-------------------------

The object returned by `.ThingClient.from_url` is an instance of a dynamically-created subclass of `.ThingClient`. Dynamically creating the class is needed because we don't know what the methods and properties should be until we have downloaded the Thing Description. However, this means most code autocompletion tools, type checkers, and linters will not work well with these classes. In the future, LabThings-FastAPI will generate custom client subclasses that can be shared in client modules, which should fix these problems (see below).

.. _things_from_things:

Using Things from other Things
------------------------------

One goal of LabThings-FastAPI is to make code portable between a client (e.g. a Jupyter notebook, or a Python script on another computer) and server-side code (i.e. code inside an action of a `.Thing`). This is done using a `.DirectThingClient` class, which is a subclass of `.ThingClient`. 

A `.DirectThingClient` class will call actions and properties of other `.Thing` subclasses using the same interface that would be used by a remote client, which means code for an action may be developed as an HTTP client, for example in a Jupyter notebook, and then moved to the server with minimal changes. Currently, there are a few differences in behaviour between working locally or remotely, most notably the return types (which are usually Pydantic models on the server, and currently dictionaries on the client). This should be improved in the future.

It is also possible for a `.Thing` to access other `.Thing` instances directly. This gives access to functionality that is only available in Python, i.e. not available through a `.ThingClient` over HTTP. However, the `.Thing` must then be supplied manually with any :ref:`dependencies` required by its actions, and the public API as defined by the :ref:`wot_td` is no longer enforced.

Actions that make use of other `.Thing` objects on the same server should access them using :ref:`dependencies`.

Planned future development: static code generation
--------------------------------------------------

In the future, `labthings_fastapi` will generate custom client subclasses. These will have the methods and properties defined in a Python module, including type annotations. This will allow static analysis (e.g. with MyPy) and IDE autocompletion to work. Most packages that provide a `Thing` subclass will want to release a client package that is generated automatically in this way. The intention is to make it possible to add custom Python code to this client, for example to handle specialised return types more gracefully or add convenience methods. Generated client code does mean there will be more packages to install on the client in order to use a particular Thing. However, the significant benefits of having a properly defined interface should make this worthwhile.

Return types are also currently not consistent between client and server code: currently, the HTTP implementation of `.ThingClient` deserialises the JSON response and returns it directly, meaning that `pydantic.BaseModel` subclasses become dictionaries. This behaviour should change in the future to be consistent between client and server. Most liekly, this will mean Pydantic models are used in both cases.



