.. _see_also:

See Also
========

LabThings-FastAPI makes quite heavy use of a few key concepts from external libraries, including `fastapi`, `pydantic`, and of course Python's core library. This page attempts to summarise these, and also acts as a useful place for docstrings to link to, so we can avoid repetition.

* LabThings makes much use of :ref:`descriptors`  - see that page for implementation details and a link to the Python descriptor documentation.
* LabThings-FastAPI uses `FastAPI <https://fastapi.tiangolo.com/>`_ to implement the HTTP server and generate OpenAPI documentation. This documentation uses intersphinx to link to specific `fastapi` classes and functions where appropriate.
* LabThings-FastAPI uses `pydantic <https://docs.pydantic.dev/latest/>`_ to define data models for action inputs and outputs, and for property values. This documentation uses intersphinx to link to specific `pydantic` classes and functions where appropriate.