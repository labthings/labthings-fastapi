.. _labthings_cc:

LabThings Core Concepts
=======================

LabThings FastAPI is a ground-up rewrite of LabThings using FastAPI. Many of the core concepts from FastAPI such as dependency injection are used heavily

The LabThings Server
--------------------

At its core LabThings FastAPI is a server-based framework. To use LabThings FastAPI a LabThings Server is created, and `.Thing` objects are added to the the server to provide functionality.

The server API is accessed over an HTTP requests, allowing client code (see below) to be written in any language that can send an HTTP request.

Everything is a Thing
---------------------

As described in :ref:`wot_cc`, a Thing represents a piece of hardware or software. LabThings-FastAPI automatically generates a :ref:`wot_td` to describe each Thing. Each function offered by the Thing is either a Property or Action (LabThings-FastAPI does not yet support Events). These are termed "interaction affordances" in WoT_ terminology.

Code on the LabThings FastAPI Server is composed of Things, however these can call generic Python functions/classes. The entire HTTP API served by the server is defined by `.Thing` objects. As such the full API is composed of the actions and properties (and perhaps eventually events) defined in each Thing.

_`WoT`: wot_core_concepts

Properties vs Settings
----------------------

A Thing in LabThings-FastAPI can have Settings as well as Properties. "Setting" is LabThings-FastAPI terminology for a "Property" with a value that persists after the server is restarted. All Settings are Properties, and -- except for persisting after a server restart -- Settings are identical to any other Properties.

Client Code
-----------

Clients or client code (Not to be confused with a `.ThingClient`, see below) is the terminology used to describe any software that uses HTTP requests to access the LabThing Server. Clients can be written in any language that supports an HTTP request. However, LabThings FastAPI provides additional functionality that makes writing client code in Python easier.

ThingClients
------------

When writing client code in Python it would be possible to formulate every interaction as an HTTP request. This has two major downsides:

1. The code must establish a new connection to the server for each request.
2. Each request is formulated as a string pointing to the endpoint and ``json`` headers for sending any data. This leads to very messy code.

Ideally the client would be able to run the `Thing` object's actions and read its properties in native python code. However, as the client code is running in a different process, and probably in a different python environment (or even on a different machine entirely!) there is no way to directly import the Python objectfor the `Thing`.

To mitigate this client code can ask the server for a description of all of a `Thing`'s properties and actions, this is known as a `ThingDescription`. From this `ThingDescription` the client code can dynamically generate a new object with methods matching each `ThingAction` and properties matching each `ThingProperty`. **This dynamically generated object is called a ThingClient**.

The :class:`.ThingClient` also handle supplying certain arguments to ThingActions without them needing to be explicitly passed each time the method is called. More detail on this is provided in the :doc:`dependencies/dependencies` page.

DirectThingClients
------------------

When writing code to run on the server one Thing will need to call another Thing. Ideally this code should be identical to code written in a client. This way the code can be prototyped in a client notebook before being ported to the server.

It would be possible to directly call the Thing object, however in this case the Python API would not be the same as for client code, because the dependencies would not automatically be supplied.
**RICHARD, Are there other reasons too?**

To provide the same interface in server code as is provided in client code LabThings FastAPI can dynamically create a new object with the same (or at least very similar) API as the `ThingClient`, this is called a **DirectThingClient**.

The key difference between a `ThingClient` and a `DirectThingClient` is that the `ThingClient` calls the `Thing` over HTTP from client code, whereas the `DirectThingClient` calls directly through the Python API from within the Server.



