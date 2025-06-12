Concurrency in `labthings-fastapi`
==================================

One of the major challenges when controlling hardware, particularly from web frameworks, is concurrency. Most web frameworks assume resources (database connections, object storage, etc.) may be instantiated multiple times, and often initialise or destroy objects as required. In contrast, hardware can usually only be controlled from one process, and usually is initialised and shut down only once.

`labthings-fastapi` instantiates each `Thing` only once, and runs all code in a thread. More specifically, each time an action is invoked via HTTP, a new thread is created to run the action. Similarly, each time a property is read or written, a new thread is created to run the property method. This means that `Thing` code should protect important variables or resources using locks from the `threading` module, and need not worry about writing asynchronous code.

In the case of properties, the HTTP response is only returned once the `Thing` code is complete. Actions currently return a response immediately, and must be polled to determine when they have completed. This behaviour may change in the future, most likely with the introduction of a timeout to allow the client to choose between waiting for a response or polling.

Many of the functions that handle HTTP requests are asynchronous, running in an `anyio` event loop. This enables many HTTP connections to be handled at once with good efficiency. The interface between async and threaded code is provided by a "Blocking Portal" created when the LabThings server is started. A FastAPI Dependency allows the blocking portal to be obtained: while it's very unlikely more than one LabThings server will exist in one Python instance, we avoid referring to the blocking portal globally in an effort to avoid concurrency issues.

If threaded code needs to call code in the `anyio` event loop, the blocking portal dependency should be used. There are relatively few occasions when `Thing` code will need to consider this explicitly: more usually the blocking portal will be obtained by a LabThings function, for example the `MJPEGStream` class.

When one `Thing` calls the actions or properties of another `Thing`, either directly or via a `DirectThingClient`, no new threads are spawned: the action or property is run in the same thread as the caller. This mirrors the behaviour of the `ThingClient`, which blocks until the action or property is complete.

