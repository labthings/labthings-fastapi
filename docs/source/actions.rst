.. _actions:

Actions
=======

Actions are the way `.Thing` objects are instructed to do things. In Python
terms, any method of a `.Thing` that we want to be able to call over HTTP
should be decorated as an Action, using :deco:`.thing_action`.

This page gives an overview of how actions are implemented in LabThings-FastAPI.
wot_cc_ includes a section on wot_actions_ that introduces the general concept.

Running actions via HTTP
------------------------

LabThings-FastAPI allows these methods to be invoked over HTTP, and
each invocation runs in its own thread. Currently, the ``POST`` request that
invokes an action will return almost immediately with a ``201`` code, and a
JSON payload that describes the invocation as an `.InvocationModel`. This includes
a link ``href`` that can be polled to check the status of the invocation.

The HTTP implementation of `.ThingClient` first makes a ``POST`` request to
invoke the action, then polls the invocation using the ``href`` supplied.
Once the action has finished (i.e. its status is ``completed``, ``error``, or
``cancelled``), its output (the return value) is retrieved and used as the
return value.

On the server, when an action is invoked over HTTP, we create a new
`.Invocation`, which is a subclass of `threading.Thread`, to run it in parallel
with other code, and keep track of its progress. The log output and return value
are held by the `.Invocation` object.

Actions are supported in LabThings-FastAPI by an `.ActionManager`, responsible
for keeping track of all the running and recently-completed Actions. This is
where Invocation-related HTTP endpoints are handled, including listing all the
`.Invocation` objects and returning the status of an individual `.Invocation`.

Running actions from other actions
----------------------------------

If code running in a `.Thing` runs methods belonging either to that `.Thing`
or to another `.Thing` on the same server, no new thread is created: the
called action runs in the same thread as the calling action, just like any
other Python code.

Action inputs and outputs
-------------------------
The code that implements an action is a method of a `.Thing`, meaning it is
a function. The input parameters are the function's arguments, and the output
parameter is the function's return value. Type hints on both arguments and
return value are used to document the action in the OpenAPI description and
the Thing Description, so it is important to use them consistently.

There are some function arguments that are not considered input parameters.
The first is ``self`` (the first positional argument), which is always the
`.Thing` on which the argument is defined. The other special arguments are
dependencies_, which use annotated type hints to tell LabThings to
supply resources needed by the action. Most often, this is a way of accessing
other `.Things` on the same server.
