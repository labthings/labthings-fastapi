.. _concurrency:

Concurrency in LabThings-FastAPI
==================================

One of the major challenges when controlling hardware, particularly from web frameworks, is concurrency. Most web frameworks assume resources (database connections, object storage, etc.) may be instantiated multiple times, and often initialise or destroy objects as required. In contrast, hardware can usually only be controlled from one process, and usually is initialised and shut down only once.

LabThings-FastAPI instantiates each :class:`.Thing` only once, and runs all code in a thread. More specifically, each time an action is invoked via HTTP, a new thread is created to run the action. Similarly, each time a property is read or written, a new thread is created to run the property method. This means that :class:`.Thing` code should protect important variables or resources using locks from the `threading` module, and need not worry about writing asynchronous code.

In the case of properties, the HTTP response is only returned once the `.Thing` code is complete. Actions currently return a response immediately, and must be polled to determine when they have completed. This behaviour may change in the future, most likely with the introduction of a timeout to allow the client to choose between waiting for a response or polling.

Many of the functions that handle HTTP requests are asynchronous, running in an :mod:`anyio` event loop. This enables many HTTP connections to be handled at once with good efficiency. The `anyio documentation`_ describes the functions that link between async and threaded code. When the LabThings server is started, we create an :class:`anyio.from_thread.BlockingPortal`, which allows threaded code to run code asynchronously in the event loop.

An action can run async code using its server interface. See `.ThingServerInterface.start_async_task_soon` for details.

There are relatively few occasions when `.Thing` code will need to consider this explicitly: more usually the blocking portal will be obtained by a LabThings function, for example the `.MJPEGStream` class.

.. _`anyio documentation`: https://anyio.readthedocs.io/en/stable/threads.html

Calling Things from other Things
--------------------------------

When one `Thing` calls the actions or properties of another `.Thing`, either directly or via a `.DirectThingClient`, no new threads are spawned: the action or property is run in the same thread as the caller. This mirrors the behaviour of the `.ThingClient`, which blocks until the action or property is complete. See :doc:`using_things` for more details on how to call actions and properties of other Things.

Invocations and concurrency
---------------------------

Each time an action is run ("invoked" in :ref:`wot_cc`), we create a new thread to run it. This thread has a context variable set, such that ``lt.cancellable_sleep`` and ``lt.get_invocation_logger`` are aware of which invocation is currently running. If an action spawns a new thread (e.g. using `threading.Thread`\ ), this new thread will not have an invocation ID, and consequently the two invocation-specific functions mentioned will not work.

Usually, the best solution to this problem is to generate a new invocation ID for the thread. This means only the original action thread will receive cancellation events, and only the original action thread will log to the invocation logger. If the action is cancelled, you must cancel the background thread. This is the behaviour of `.ThreadWithInvocationID`\ .

It is also possible to copy the current invocation ID to a new thread. This is often a bad idea, as it's ill-defined whether the exception will arise in the original thread or the new one if the invocation is cancelled. Logs from the two threads will also be interleaved. If it's desirable to log from the background thread, the invocation logger may safely be passed as an argument, rather than accessed via ``lt.get_invocation_logger``\ .
