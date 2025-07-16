r"""Resources that may be requested using annotated types.

:ref:`actions` often need to access resources outside of the host `.Thing`\ , for
example invoking actions or accessing properties on other `.Thing`\ s or
calling methods provided by the server.

:ref:`dependencies` are a `FastAPI concept`_ that is re-used in LabThings to allow
:ref:`actions` to request resources in a way that plays nicely with type hints
and is easy to intercept for testing.

There is more documentation at :ref:`dependencies` for how this works within
LabThings.

.. _`FastAPI concept`: https://fastapi.tiangolo.com/tutorial/dependencies/
"""
