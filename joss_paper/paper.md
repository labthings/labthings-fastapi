---
title: 'labthings-fastapi: A modern Web of Things framework for laboratory automation'
tags:
  - Python
  - FastAPI
  - laboratory automation
  - hardware control
  - Web of Things
  - OpenFlexure
authors:
  - name: Author Name One
    orcid: 0000-0000-0000-0000
    affiliation: "1, 2"
  - name: Author Name Two
    orcid: 0000-0000-0000-0000
    affiliation: 1
affiliations:
 - name: Institution Name One, Country
   index: 1
 - name: Institution Name Two, Country
   index: 2
date: DD Month YYYY
bibliography: paper.bib
---

# Summary

Modern laboratory experiments increasingly rely on software-controlled hardware, from microscopes and imaging systems to sensors and positioning stages. Making these instruments available over a network can enable remote operation, automated experiments, and integration with other software. However, implementing a network interface for custom laboratory hardware usually requires researchers to develop and maintain both the code that controls the instrument and a separate application programming interface (API). Developing these components separately introduces additional complexity and can result in interfaces that are specific to an individual instrument or application.

`labthings-fastapi` is a Python library designed to simplify the process of making laboratory instruments available over HTTP. Hardware functionality is represented in Python using `Thing` classes, whose properties and methods can be exposed through an HTTP API using Python type hints and decorators. For example, a microscope may expose its current stage position as a property and an image acquisition operation as an action. `labthings-fastapi` generates a network-accessible interface to this functionality together with machine-readable documentation in both OpenAPI and W3C Web of Things (WoT) Thing Description formats [@wot-td]. Exposing instrument functionality through HTTP allows clients to interact with a `Thing` using any programming language capable of making HTTP requests, while `labthings-fastapi` also provides a higher-level client interface for Python applications.

`labthings-fastapi` is a ground-up rewrite of `python-labthings`, replacing Flask and Marshmallow with FastAPI and Pydantic. The redesign uses Python type annotations and functionality provided by these modern dependencies to reduce duplicated definitions, simplify automatic documentation generation, and provide lifecycle and concurrency behaviour appropriate for physical hardware. `labthings-fastapi` is the underlying framework for version 3 of the OpenFlexure Microscope software.

# Statement of need

Software-controlled hardware is increasingly important in experimental research, particularly in the development of custom and open-source instruments. Python provides a large ecosystem for communicating with hardware, but locally controlling a device is different from making its functionality available to other software over a network. Developers creating a network interface must determine how operations and hardware state are represented, define HTTP endpoints, validate and serialise data, document the resulting interface, and manage access to physical resources. Implementing these requirements separately for individual instruments introduces additional development and maintenance work and can produce device-specific interfaces that are difficult to integrate into larger experimental systems.

`labthings-fastapi` provides a reusable framework for exposing Python-controlled laboratory hardware through HTTP. A unit of hardware or software is represented as a `Thing`, with its functionality expressed through actions and properties. Actions are defined using decorated Python methods, while properties may be defined using typed attributes or property-like decorators. Python type annotations describe action inputs and outputs and property values, allowing data validation and interface documentation to be derived from the same definitions used to implement the instrument. Researchers can therefore expose hardware functionality without separately maintaining Python methods, HTTP endpoint definitions, and schemas for the same operation.

The framework is intended for researchers developing custom or open scientific instruments, research software engineers building laboratory infrastructure, and developers integrating multiple devices into automated experimental systems. Instrument functionality exposed by `labthings-fastapi` can be accessed through HTTP by clients written in any programming language with an HTTP library. Each interface is also described in machine-readable OpenAPI and W3C Web of Things Thing Description formats [@wot-td]. The two descriptions provide complementary representations of the HTTP API and the higher-level properties and actions offered by an instrument, reducing the need for clients to rely on undocumented, instrument-specific network interfaces.

`labthings-fastapi` builds on experience gained from `python-labthings`, the original implementation of the framework. The new implementation replaces Flask and Marshmallow with FastAPI and Pydantic. FastAPI removes much of the custom code previously required to generate an OpenAPI description, while Python type annotations replace separate Marshmallow schemas and endpoint classes for defining action inputs and outputs. The revised architecture also represents separate components as multiple Things rather than combining extensions into a single large Thing, simplifying the generation of their Thing Descriptions. The changes retain the original aim of making laboratory hardware available through standardised network interfaces while reducing duplication in the code required to define those interfaces.

# State of the field

Laboratory automation software addresses the connection between experimental protocols, software, and heterogeneous physical equipment at several different levels. Projects such as PyLabRobot provide hardware-independent Python interfaces for classes of laboratory equipment, including liquid-handling robots, plate readers, and related devices [@wierenga2023]. Bluesky and Ophyd provide abstractions for experiment orchestration, data acquisition, and hardware interfaces [@bluesky; @ophyd]. These frameworks demonstrate the value of separating experimental logic from device-specific control, but address a different layer of the laboratory automation software stack. `labthings-fastapi` focuses specifically on exposing a Python representation of hardware or software as a self-describing network service, rather than providing a library of hardware drivers or a system for orchestrating complete experiments.

The W3C Web of Things provides a complementary approach to interoperability between network-connected devices. A WoT Thing Description defines machine-readable metadata and interaction affordances for a physical or virtual entity, including properties, actions, and events [@wot-td]. General-purpose WoT implementations are available for exposing and consuming Things in several programming languages [@wot-tools]. `labthings-fastapi` does not aim to replace these general-purpose WoT runtimes. Instead, the framework applies WoT concepts to Python-controlled laboratory hardware while addressing requirements associated with physical research instruments, including device lifecycle and concurrent access.

General-purpose web frameworks and physical hardware can have different lifecycle and concurrency requirements. Web applications commonly assume that resources can be instantiated or destroyed as required, whereas a hardware device may need to be initialised once and accessed by only one process. `labthings-fastapi` therefore instantiates each `Thing` once and runs hardware-facing `Thing` code in threads. HTTP request handling remains asynchronous, allowing the framework to combine FastAPI's asynchronous web infrastructure with synchronous Python code commonly used to control laboratory hardware.

The decision to develop `labthings-fastapi`, rather than extend a general-purpose WoT implementation, was driven by its role as an interface between Python hardware-control code and standards-based network APIs. Rebuilding the original `python-labthings` implementation on FastAPI and Pydantic also avoided retaining custom infrastructure now provided by widely used dependencies. FastAPI generates OpenAPI descriptions from typed Python interfaces, while Pydantic provides parsing and validation of typed data. `labthings-fastapi` combines these capabilities with generation of WoT Thing Descriptions and hardware-oriented lifecycle and concurrency semantics. Its contribution is therefore not a new hardware-driver ecosystem or experiment orchestration system, but a reusable layer for exposing Python-controlled research hardware through interoperable, self-describing network interfaces.

<!-- TODO (Beth/Richard): Confirm whether additional laboratory automation or
Web of Things frameworks were directly considered during the development of
labthings-fastapi and should be included here. Check the build-versus-contribute
argument against the team's original design decisions before submission. -->

# Software Design

`labthings-fastapi` represents units of hardware or software as subclasses of `Thing`. Properties and actions exposed by each Thing are defined using Python attributes, methods, type annotations, and decorators, allowing the implementation and network-facing description of the instrument to be maintained together. FastAPI and Pydantic use the type information to validate data and generate an OpenAPI description of the HTTP API, avoiding separate endpoint and schema definitions for much of the instrument interface.

The framework adopts concepts and vocabulary from the W3C Web of Things model [@wot-td]. Individual units of hardware or software are represented as Things, hardware state can be exposed through properties, and operations can be represented as actions. `labthings-fastapi` generates a Thing Description for each `Thing` alongside the OpenAPI description of its HTTP interface. The current implementation supports properties and actions but does not yet implement WoT events. The resulting OpenAPI and Thing Description documents provide complementary descriptions of the HTTP API and the higher-level capabilities of the instrument.

Hardware also imposes lifecycle and concurrency requirements that differ from many conventional web applications. `labthings-fastapi` creates each `Thing` once during the lifetime of a server and provides mechanisms for its start-up and shutdown. Actions invoked over HTTP and property access are run in threads, allowing `Thing` implementations to use synchronous Python code rather than requiring hardware-control code to be asynchronous. HTTP request handling uses an asynchronous event loop, separating concurrency in the web interface from the programming model presented to hardware developers.

<!-- TODO (Richard/Joel/Julian): Expand the design rationale rather than the
API documentation. In particular:
1. Explain why Thing code executes in threads rather than directly in the
   asynchronous event loop.
2. Explain the locking model and why it is useful for physical hardware.
3. Explain the design of long-running Actions, including invocation tracking,
   polling and cancellation where appropriate.
4. Confirm the rationale for the Thing lifecycle model.
5. Describe important trade-offs involved in adopting FastAPI, Pydantic and
   the WoT model.
6. Explain the role of Thing Slots if they represent an important architectural
   distinction from python-labthings.

JOSS specifically asks for design trade-offs and architectural reasoning, so
the final text should concentrate on WHY these choices were made rather than
documenting individual API functions.

We also may want figures in this section.-->

# Research impact statement

`labthings-fastapi` is the underlying framework for version 3 of the OpenFlexure Microscope software. The OpenFlexure Microscope is an open-source, automated microscope designed to be manufactured using accessible fabrication techniques [@collins2020]. Earlier work on the OpenFlexure software demonstrated the use of Web of Things concepts to simplify interactions between microscope hardware, server software, and user-facing applications [@collins2021]. `labthings-fastapi` continues this approach using a redesigned implementation based on FastAPI and Pydantic.

The wider OpenFlexure project has supported research across a range of microscopy and laboratory applications [@collins2020; @knapper2024]. Within OpenFlexure Microscope version 3, `labthings-fastapi` provides the framework through which microscope functionality is exposed as a documented HTTP interface and represented through Web of Things concepts.

<!-- TODO (Ben/Joe/Richard): Add concrete evidence of the impact specifically
attributable to labthings-fastapi rather than OpenFlexure generally.

Suggested evidence:
- current deployment/use of OpenFlexure Microscope v3;
- the Microscope Farm case study;
- number or type of microscopes/installations using the v3 software, if there
  is a defensible source for this;
- research workflows directly using the labthings-fastapi interface;
- external users, downstream projects, or integrations;
- publications or datasets produced using the v3 software.

JOSS requires evidence of realised research impact or credible and specific
near-term significance, rather than purely aspirational statements.

We also may want figures in this section-->

# AI Usage Disclosure

<!-- TODO before submission: Complete the AI usage disclosure after establishing
the full use of generative AI across the software, documentation, and paper.
The final disclosure must comply with the current JOSS AI usage policy,
including the tools/models used, the nature and scope of their assistance, and
confirmation of human review and validation. -->

# Acknowledgements

<!-- TODO (Richard):
We acknowledge contributions from [Name] during the early development of this
project, and funding from [Grant Name/Number] which supported this work. -->

# References
