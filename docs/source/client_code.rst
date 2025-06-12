Client code
===========

The interface to a `Thing` is defined by its interaction affordances, which are defined in the Thing Description. The `labthings-fastapi.client` library provides a `ThingClient` class to interact with a `Thing` via HTTP. This is a class with a method for each Action, and a property for each Property of the Thing. The intention is to provide a simple, pythonic interface that plays nicely with IDEs and autocompletion. 

An additional goal is to provide an interface that is consistent between the server and client code: a `DirectThingClient` class is used by the `labthings-fastapi` server to call actions and properties of other `Thing`s, which means code for an action may be developed as an HTTP client, for example in a Jupyter notebook, and then moved to the server with minimal changes. Currently, there are a few differences in behaviour between local and remote `Thing`s, most notably the return types (which are usually Pydantic models on the server, and currently dictionaries generated from JSON on the client). This should be improved in the future.

Client code generation
----------------------

Currently, most clients are created using the class method `ThingClient.from_url`. This returns an instance of a dynamically-created subclass, rather than a `ThingClient` instance directly. The subclass is required in order to add methods and properties corresponding to the Thing Description sent by the server. While this is a solution that should work immediately, it does not work well with code completion or static analysis, and client objects must be introspected on-the-fly.

In the future, `labthings_fastapi` will generate custom client subclasses. These will have the methods and properties defined in a Python module, including type annotations. This will allow static analysis (e.g. with MyPy) and IDE autocompletion to work. Most packages that provide a `Thing` subclass will want to release a client package that is generated automatically in this way. The intention is to make it possible to add custom Python code to this client, for example to handle specialised return types more gracefully or add convenience methods.





