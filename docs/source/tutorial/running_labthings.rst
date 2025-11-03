.. _tutorial_running:

Running LabThings-FastAPI
=========================

Each time you want to use LabThings-FastAPI, you will need to open a terminal and activate your virtual environment. If you created a virtual environment using the command on the :doc:`installing_labthings` page, you will need to change directory to the folder where you created your virtual environment (using `cd`) and then activate the virtual environment with `source .venv/bin/activate` or `.venv/Scripts/activate` (on Windows).

Once you have activated the virtual environment, you should be able to run an example server with the command:

.. code-block:: bash

    labthings-server --json '{"things":{"mything":"labthings_fastapi.example_things:MyThing"}}'

This command will start a LabThings server, and will print the root URL for your server (by default, ``http://127.0.0.1:5000``). The ``127.0.0.1`` part means the server is only accessible from your computer, so you don't need to worry about other computers on your network accessing it.

Now that your server is running, you should be able to view the interactive documentation in your web browser. There is an OpenAPI documentation page at ``http://127.0.0.1:5000/docs/``. This shows all the requests that the server supports, and even allows you to try them out in the web browser.

Another important document is the Thing Description: this is a higher-level description of all the capabilities of each Thing in the server. For our example server, we have just one Thing, which is at ``http://127.0.0.1:5000/mything/``. This is a JSON document, but if you view it in Firefox there is a convenient tree view that makes it easier to navigate. Currently the Thing Description is not as interactive as the OpenAPI documentation, but it is rather neater as it's a higher-level description: rather than describing every possible request, it describes the capabilities of your Thing in a way that should correspond nicely to the code you might write using a Python client object, or a client in some other language.

.. _config_files:

Configuration files
-------------------

It is worth unpicking the command you ran to start the server: it has one argument, which is a JSON string. This is fine if you are starting up a test server for one Thing, but it gets unwieldy very quickly. Most of the time, you will want to start the server with a configuration file. This is a JSON file that contains the same information as the JSON string you passed to the command above, but in a more convenient format. To do this, create a file called `example_things.json` in the same directory as your virtual environment, and put the following content in it:

.. code-block:: json

    {
        "things": {
            "mything": "labthings_fastapi.example_things:MyThing"
        }
    }

You can then start the server using the command:

.. code-block:: bash

    labthings-server --config example_things.json

