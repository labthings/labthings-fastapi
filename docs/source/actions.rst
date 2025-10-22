.. _actions:

Actions
=======

Actions are the way `.Thing` objects are instructed to do things. In Python
terms, any method of a `.Thing` that we want to be able to call over HTTP
should be decorated as an Action, using :deco:`.thing_action`.

This page gives an overview of how actions are implemented in LabThings-FastAPI.
:ref:`wot_cc` includes a section on :ref:`wot_actions` that introduces the general concept.

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
:ref:`dependencies`, which use annotated type hints to tell LabThings to
supply resources needed by the action. Most often, this is a way of accessing
other `.Things` on the same server.

.. action_logging:
Logging from actions
--------------------
Action code should use `.Thing.logger` to log messages. This will be configured
to handle messages on a per-invocation basis and make them available when the action
is queried over HTTP.

This may be used to display status updates to the user when an action takes
a long time to run, or it may simply be a helpful debugging aid. 

See :mod:`.logs` for details of how this is implemented.

.. action_cancellation:
Cancelling actions
------------------
If an action could run for a long time, it is useful to be able to cancel it
cleanly. LabThings makes provision for this by allowing actions to be cancelled
using a ``DELETE`` HTTP request. In order to allow an action to be cancelled,
you must give LabThings opportunities to interrupt it. This is most often done
by replacing a `time.sleep()` statement with `.cancellable_sleep()` which
is equivalent,  but will raise an exception if the action is cancelled.

For more advanced options, see `.invocation_contexts` for detail.

.. invocation_context:
Invocation contexts
-------------------
Cancelling actions and capturing their logs requires action code to use a
specific logger and check for cancel events. This is done using `contextvars`
such that the action code can use module-level symbols rather than needing
to explicitly pass the logger and cancel hook as arguments to the action
method.

Usually, you don't need to consider this mechanism: simply use the invocation
logger or cancel hook as explained above. However, if you want to run actions
outside of the server (for example, for testing purposes) or if you want to
call one action from another action, but not share the cancellation signal
or log, functions are provided in `.invocation_contexts` to manage this.

If you start a new thread from an action, code running in that thread will
not have the invocation ID set in a context variable. A subclass of
`threading.Thread` is provided to do this, `.ThreadWithInvocationID`\ .

Raising exceptions
------------------
If an action raises an unhandled exception, the action will terminate with an Error
status and LabThings will log the error and the traceback.

In the case where the error has been handled, but the job needs to terminate the action
should raise an InvocationError (or a error which subclasses this). The message from
this exceptions will be logged, but the full traceback will not be logged as this error
has been handled.
