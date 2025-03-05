.. labthings-fastapi documentation master file, created by
   sphinx-quickstart on Wed May 15 16:34:51 2024.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to labthings-fastapi's documentation!
=============================================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   core_concepts.rst
   quickstart/quickstart.rst
   dependencies/dependencies.rst

   apidocs/index

`labthings-fastapi` implements a Web of Things interface for laboratory hardware using Python. This is a ground-up rewrite of python-labthings_, replacing Flask 1 and Marshmallow with FastAPI and Pydantic. It is the underlying framework for v3 of the `OpenFlexure Microscope software <https://gitlab.com/openflexure/openflexure-microscope-server/>`_.

Features include:

* Alignment with the `W3C Web of Things <https://www.w3.org/WoT/>`_ standard (see :doc:`core_concepts`)
    - Things are classes, with properties and actions defined exactly once
    - Various improvements to TD generation and validation with `pydantic`
* Cleaner API
    - Datatypes of action input/outputs and properties are defined with Python type hints
    - Actions are defined exactly once, as a method of a `Thing` class
    - Properties and actions are declared using decorators (or descriptors if that's preferred)
    - Dependency injection is used to manage relationships between Things and dependency on the server
* Async HTTP handling
    - Starlette (used by FastAPI) can handle requests asynchronously - potential for websockets/events (not used much yet)
    - `Thing` code is still, for now, threaded. I intend to make it possible to write async things in the future, but don't intend it to become mandatory
* Smaller codebase
    - FastAPI more or less completely eliminates OpenAPI generation code from our codebase
    - Thing Description generation is very much simplified by the new structure (multiple Things instead of one massive Thing with many extensions)


Installation
------------

``pip install labthings-fastapi``

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

.. _python-labthings: https://github.com/labthings/python-labthings/