r"""Resources that may be requested using annotated types.

actions_ often need to access resources outside of the host `.Thing`\ , for
example invoking actions or accessing properties on other `.Thing`\ s or
calling methods provided by the server.

dependencies_ are a `FastAPI concept`_ that is re-used in LabThings to allow
actions_ to request resources in a way that plays nicely with type hints
and is easy to intercept for testing.

There is more documentation at dependencies_ for how this works within
LabThings.

.. _`FastAPI concept`: https://fastapi.tiangolo.com/tutorial/dependencies/
"""
