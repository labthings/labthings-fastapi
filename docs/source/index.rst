Documentation for LabThings-FastAPI
=============================================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   quickstart/quickstart.rst
   wot_core_concepts.rst
   structure.rst
   tutorial/index.rst
   examples.rst
   actions.rst
   thing_slots.rst
   dependencies/dependencies.rst
   blobs.rst
   concurrency.rst
   using_things.rst
   see_also.rst

   autoapi/index

`labthings-fastapi` is a Python library to simplify the process of making laboratory instruments available via a HTTP. It aims to create an API that is usable from any modern programming language, with API documentation in both :ref:`openapi` and :ref:`gen_td` formats. It is the underlying framework for v3 of the `OpenFlexure Microscope software <https://gitlab.com/openflexure/openflexure-microscope-server/>`_. Key features and design aims are:

* The functionality of a unit of hardware or software is described using `.Thing` subclasses.
* Methods and properties of `.Thing` subclasses may be added to the HTTP API and associated documentation using decorators.
* Datatypes of action input/outputs and properties are defined with Python type hints.
* Actions are decorated methods of a `.Thing` class. There is no need for separate schemas or endpoint definitions.
* Properties are defined either as typed attributes (similar to `pydantic` or `dataclasses`) or with a `property`\ -like decorator.
* Lifecycle and concurrency are appropriate for hardware: `Thing` code is always run in a thread, and each `Thing` is instantiated, started up, and shut down only once.
* Vocabulary and concepts are aligned with the `W3C Web of Things <https://www.w3.org/WoT/>`_ standard (see :doc:`wot_core_concepts`)

Previous version
----------------

This is a ground-up rewrite of python-labthings_, replacing Flask 1 and Marshmallow with FastAPI and Pydantic. 
Compared to `python-labthings`_, this framework updates dependencies, shrinks the codebase, and simplifies the API  (see :doc:`structure`).
* FastAPI more or less completely eliminates OpenAPI generation code from our codebase
* Marshmallow schemas and endpoint classes are replaced with Python type hints, eliminating double- or triple-definition of actions and their inputs/outputs.
* Thing Description generation is very much simplified by the new structure (multiple Things instead of one massive Thing with many extensions)


Installation
------------

``pip install labthings-fastapi``

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

.. _python-labthings: https://github.com/labthings/python-labthings/
.. _FastAPI: https://fastapi.tiangolo.com/
.. _pydantic: https://pydantic-docs.helpmanual.io/