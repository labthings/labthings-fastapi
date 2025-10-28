.. _labthings_cc:
.. _labthings_structure:

LabThings structure
===================

LabThings is intended to simplify the process of making a piece of hardware available through an HTTP API and documenting that API with :ref:`gen_docs`\ .

Server
------

LabThings is a server-based framework.
The `.ThingServer` creates and manages the `.Thing` instances that represent individual hardware or software units. The functionality of those `.Thing`\ s is accessed via HTTP requests, which can be made from a web browser, the command line, or any programming language with an HTTP library.

LabThings-FastAPI is built on top of `fastapi`\ , which is a fast, modern HTTP framework. LabThings provides functionality to manage `.Thing`\ s and their actions, including:

* Initialising, starting up, and shutting down the `.Thing` instances, so that hardware is correctly started up and shut down.
* Managing actions, including making logs and output values available over HTTP.
* Managing `.Blob` input and output (i.e. binary objects that are best not serialised to JSON).
* Generating a :ref:`gen_td` in addition to the :ref:`openapi` documentation produced by `fastapi`\ .
* Making connections between `.Thing` instances as required.

`.Thing`\ s
-----------

Each unit of hardware (or software) that should be exposed by the server is implemented as a subclass of `.Thing`\ . A `.Thing` subclass represents a particular type of instrument (whether hardware or software), and its functionality is described using actions and properties, described below. `.Thing`\ s don't have to correspond to separate pieces of hardware: it's possible (and indeed recommended) to use `.Thing` subclasses for software components, plug-ins, swappable modules, or anything else that needs to add functionality to the server. `.Thing`\ s may access each other's attributes, so you can write a `.Thing` that implements a particular measurement protocol or task, using hardware that's accessed through other `.Thing` instances on the server. Each `.Thing` is documented by a :ref:`gen_td` which outlines its features in a higher-level way than :ref:`openapi`\ .

The attributes of a `.Thing` are made available over HTTP by decorating or marking them with the following functions:

* `.property` may be used as a decorator analogous to Python's built-in ``@property``\ . It can also be used to mark class attributes as variables that should be available over HTTP.
* `.setting` works similarly to `.property` but it is persisted to disk when the server stops, so the value is remembered.
* `.thing_action` is a decorator that makes methods available over HTTP.
* `.thing_slot` tells LabThings to supply an instance of another `.Thing` at runtime, so your `.Thing` can make use of it.

..

    `.Thing` Lifecycle
    ------------------

    As a `.Thing` often represents a piece of hardware, it can't be dynamically created and destroyed in the way many resources of web applications are. In LabThings, the lifecycle of a Thing calls several methods to manage the hardware and configuration. In order, these are:

    * ``__init__`` is called when the `.Thing` is created by the server. It shouldn't talk to the hardware yet, but it may store its arguments as configuration. For example, you might accept 

    When implementing a `.Thing` it is important to include code to set up any required hardware connections in ``__enter__`` and code to shut it down again in ``__exit__`` as this will be used by the server to set up and tear down the hardware connections. The ``__init__`` method is called when the `.Thing` is first created by the server, and is primarily used 


Client Code
-----------

Client code can be written in any language that supports an HTTP request. However, LabThings FastAPI provides additional functionality that makes writing client code in Python easier.

`.ThingClient` is a class that wraps up the required HTTP requests into a simpler interface. It can retrieve the :ref:`gen_td` over HTTP and use it to generate a new object with methods matching each `.thing_action` and properties matching each `.property`.

While the current dynamic implementation of `.ThingClient` can be inspected with functions like `help` at runtime, it does not work well with static tools like `mypy` or `pyright`\ . In the future, LabThings should be able to generate static client code that works better with autocompletion and type checking.