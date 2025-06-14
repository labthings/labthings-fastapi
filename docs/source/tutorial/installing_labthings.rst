Installing LabThings-FastAPI
============================

LabThings-FastAPI is a Python package, which is published to PyPI. You can install `labthings-fastapi` using `pip`. To see compatible versions of Python, please check PyPI_.

It is common practice to use virtual environments in Python: this isolates projects from each other, and makes sure that installing packages for one project doesn't break other work you are doing. There are many ways of managing virtual environments in Python: if you are using a distribution like Anaconda, you may prefer to manage environments using the `conda` command or Anaconda interface. This tutorial uses the built-in `venv` module to create a virtual environment, but you can use whatever tool you are happy with.

The commands below are all intended to be run in a terminal. We tend to use PowerShell on Windows, Terminal on a mac or your preferred terminal utility if you are on Linux. Note that most of our automated testing runs on Linux, and one or two commands are different on Windows. This is indicated with a comment (some text after a ``#`` character).

It's always a good idea to check your Python version before you start, by running ``python --version``. This should print out something like ``Python 3.12.3``, although the exact version is not particularly important so long as it's up to date enough for the package to install. If this doesn't work, you likely need to install Python, which this tutorial doesn't cover. The Python website has instructions for most common operating systems.

To create a virtual environment, run the following command:

.. literalinclude:: ../quickstart/quickstart_example.sh
    :language: bash
    :start-after: BEGIN venv
    :end-before: END venv
    
then install labthings with:

.. literalinclude:: ../quickstart/quickstart_example.sh
    :language: bash
    :start-after: BEGIN install
    :end-before: END install

It is also possible to install LabThings from source, by cloning the GitHub repository and running ``pip install -e .[dev]``, but this is only recommended if you intend to alter the LabThings-FastAPI library; it is best to use the published package unless you have a good reason not to.

.. _PyPI: https://pypi.org/project/labthings-fastapi/