Web of Things Core Concepts
===========================

LabThings is rooted in the `W3C Web of Things standards <WoT>`_. Using IP networking in labs is not new, though perhaps under-used. However lack of proper standardisation has stiffled widespread adoption. LabThings, rather than try to introduce new competing standards, uses the architecture and terminology introduced by the W3C Web of Things. A full description of the core architecture can be found in the `Web of Things (WoT) Architecture <https://www.w3.org/TR/wot-architecture/#sec-wot-architecture>`_ document. However, a brief outline of the concepts relevant to `labthings-fastapi` is given below.

Thing
---------

A `Thing` represents a piece of hardware or software. It could be a whole instrument (e.g. a microscope), a component within an instrument (e.g. a translation stage or camera), or a piece of software (e.g. code to tile together large area scans). `Thing`s in `labthings-fastapi` are Python classes that define Properties, Actions, and Events (see below). A Thing (sometimes called a "Web Thing") is defined by W3C as "an abstraction of a physical or a virtual entity whose metadata and interfaces are described by a WoT Thing description."

`labthings-fastapi` automatically generates a `Thing Description`_ to describe each `Thing`. Each function offered by the `Thing` is either a Property, Action, or Event. These are termed "interaction affordances" in WoT_ terminology.

Properties
----------

As a rule of thumb, any attribute of your device that can be quickly read, or optionally written, should be a Property. For example, simple device settings, or status information (like a temperature) that takes negligible time to measure. Reading a property should never be a slow operation, as it is expected to be called frequently by clients. Properties are defined as "an Interaction Affordance that allows to read, write, or observe a state of the Thing" in the WoT_ standard. Similarly, writing to a property ought to be quick, and should not cause equipment to perform long-running operations. Properties are defined very similar to standard Python properties, using a decorator that adds them to the `Thing Description`_ and the HTTP API.

Actions
-------

Actions generally correspond to making equipment (or software) do something. For example, starting a data acquisition, moving a stage, or changing a setting that requires a significant amount of time to complete. The key point here is that Actions are typically more complex in functionality than simply setting or getting a property. For example, they can set multiple properties simultaneously (for example, auto-exposing a camera), or they can manipulate the state of the Thing over time, for example starting a long-running data acquisition.

`labthings-fastapi` runs actions in background threads. This allows other actions and properties to be accessed while it is running. You define actions as methods of your `Thing` class using the decorator.

Events
------

An event "describes an event source that pushes data asynchronously from the Thing to the Consumer. Here not state, but state transitions (i.e., events) are communicated. Events MAY be triggered through conditions that are not exposed as Properties."

Common examples are notifying clients when a Property is changed, or when an Action starts or finishes. However, Thing developers can introduce new Events such as warnings, status messages, and logs. For example, a device may emit an events when the internal temperature gets too high, or when an interlock is tripped. This Event can then be pushed to both users AND other Things, allowing automtic response to external conditions.

A good example of this might be having Things automatically pause data-acquisition Actions upon detection of an overheat or interlock Event from another Thing. Events are not currently implemented in `labthings-fastapi`, but are planned for future releases.

.. _WoT: https://www.w3.org/WoT/
.. _Thing Description: https://www.w3.org/TR/wot-thing-description/