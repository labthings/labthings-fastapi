Quick start
===========

You can install `labthings-fastapi` using `pip`. Create a virtual environment for you project, then install labthings with:

.. code-block:: bash

    pip install labthings-fastapi[server]

To define a simple example ``Thing``, paste the following into a python file, ``counter.py``:

.. literalinclude:: counter.py
    :language: python
    
``counter.py`` defines the ``TestThing`` class, and then runs a LabThings server in its ``__name__ == "__main__"`` block. This means we should be able to run the server with:

.. code-block:: bash

    python counter.py

Visiting http://localhost:5000/counter/ will show the thing description, and you can interact with the actions and properties using the Swagger UI at http://localhost:5000/docs/.

You can also interact with it from another Python instance, for example by running:

.. literalinclude:: counter_client.py
    :language: python

It's best to write ``Thing`` subclasses in Python packages that can be imported. This makes them easier to re-use and distribute, and also allows us to run a LabThings server from the command line, configured by a configuration file. An example config file is below:

.. literalinclude:: example_config.json
    :language: JSON

Paste this into ``example_config.json`` and then run a server using:

.. code-block:: bash

    labthings-server -c example_config.json

Bear in mind that this won't work if `counter.py` above is still running - both will try to use port 5000. 

As before, you can visit http://localhost:5000/docs or http://localhost:5000/example/ to see the OpenAPI docs or Thing Description, and you can use the Python client module with the second of those URLs.