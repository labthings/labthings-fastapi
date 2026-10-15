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

Modern laboratory experiments increasingly rely on software-controlled hardware, from microscopes and imaging systems to sensors and positioning stages. Making these instruments available over a network can enable remote operation, automated experiments, and integration with other software. However, implementing a network interface for custom laboratory hardware usually requires researchers to maintain both device-control code and a separate application programming interface (API), increasing development effort and encouraging instrument-specific solutions.

`labthings-fastapi` is a Python library for exposing laboratory instruments and scientific software through HTTP. Hardware functionality is represented using Thing classes, whose properties and methods can be exposed as network-accessible properties and actions using Python type hints and decorators. The framework automatically generates machine-readable descriptions of both the HTTP API (OpenAPI) and higher-level device capabilities (W3C Web of Things Thing Descriptions) [@wot-td].

Representing instruments as network-accessible services decouples experimental software from device-specific implementations. User interfaces, automated workflows, data-processing pipelines, and remote clients can interact with the same instrument through a standard interface, allowing software written in different programming languages, operating systems, or execution environments to be combined within a single experimental system.

`labthings-fastapi` is a ground-up rewrite of `python-labthings`, replacing Flask and Marshmallow with FastAPI and Pydantic [@python-labthings]. The redesign reduces duplicated interface definitions, simplifies documentation generation, and provides lifecycle and concurrency behaviour appropriate for physical hardware. `labthings-fastapi` forms the underlying framework of version 3 of the OpenFlexure Microscope software [@openflexure-microscope-server].

# Statement of need

Software-controlled hardware is increasingly important in experimental research, particularly in the development of custom and open-source scientific instruments. Python provides a rich ecosystem for communicating with hardware, but making a device accessible to other software over a network introduces additional challenges. Developers must define HTTP endpoints, validate and serialise data, document interfaces, and manage access to physical resources. Implementing these capabilities separately for each instrument creates additional maintenance burden and can produce interfaces that are difficult to integrate into larger experimental systems.

Beyond reducing development effort, standardised HTTP interfaces change how laboratory software can be composed. Experimental workflows frequently combine graphical user interfaces, automated scripts, data-processing services, and instrument-control software running on different machines and written in different languages. Exposing instruments through web-based interfaces allows these components to communicate using widely supported standards rather than bespoke integrations. By building on web technologies developed to support communication between distributed software systems, laboratory automation can leverage mature solutions for interoperability, concurrency, and remote access rather than requiring instrument developers to implement these capabilities independently. A researcher may therefore operate an instrument through a graphical interface while simultaneously incorporating the same device into an automated workflow, without needing to manage low-level concurrency between front-end and hardware-control software.

`labthings-fastapi` provides a reusable framework for exposing laboratory devices and scientific software through HTTP. A unit of hardware or software is represented as a Thing, with functionality expressed through actions and properties. Python type annotations define action inputs, outputs, and property values, enabling data validation and interface documentation to be derived directly from the implementation rather than maintained separately. The framework is intended for researchers developing scientific instruments, research software engineers building laboratory infrastructure, and developers integrating multiple devices into automated experimental systems. Instrument functionality can be accessed from any language capable of making HTTP requests, while OpenAPI and W3C Web of Things descriptions provide machine-readable representations of both the underlying API and the higher-level capabilities of an instrument [@wot-td]. These descriptions reduce reliance on bespoke documentation and support integration of heterogeneous devices into larger experimental systems.

# State of the field

The adoption of web technologies for laboratory automation is motivated not only by interoperability but also by the maturity of the surrounding software ecosystem. Web-based systems routinely support concurrent interaction between many users and services. Laboratory environments exhibit similar requirements: instruments must remain accessible to multiple applications, user interfaces should remain responsive during long-running operations, and software components may execute on different machines. Building on HTTP and WoT standards allows laboratory automation software to leverage a mature communication infrastructure while abstracting much of the complexity of concurrent instrument control.

The W3C Web of Things (WoT) provides a complementary approach to interoperability between network-connected devices. A WoT Thing Description defines machine-readable metadata and interaction affordances for a physical or virtual entity, including properties, actions, and events [@wot-td]. General-purpose WoT implementations are available for exposing and consuming Things in several programming languages [@wot-tools]. However, these frameworks are not specifically designed around the lifecycle and concurrency requirements of scientific hardware. Hololinked applies Web of Things concepts to instrumentation and data-acquisition systems, providing a protocol-flexible framework supporting multiple communication backends [@hololinked]. In contrast, `labthings-fastapi` applies these standards through FastAPI to support network-accessible laboratory instrumentation and scientific software.

Laboratory automation software addresses the connection between experimental protocols, software, and physical equipment at several levels. Python-Microscope provides hardware abstraction layers and network-accessible control for microscopy devices [@python-microscope], while Pycro-Manager enables programmatic control of microscopy systems for hardware automation and image acquisition through the Micro-Manager ecosystem [@pinkard2021]. PyLabRobot provides hardware-independent interfaces for laboratory equipment including liquid-handling robots, plate readers, and related devices [@wierenga2023]. At a higher level, Bluesky and Ophyd provide abstractions for experiment orchestration, data acquisition, and hardware interfaces [@bluesky; @ophyd]. These frameworks demonstrate the value of separating experimental logic from device-specific control, but focus primarily on hardware abstraction or experiment orchestration rather than exposing arbitrary laboratory devices and scientific software as self-describing network services.

`labthings-fastapi` occupies a distinct position within this ecosystem. Existing frameworks typically focus on hardware abstraction, instrument-specific control, experiment orchestration, or general-purpose WoT infrastructure. In contrast, labthings-fastapi addresses the intermediate problem of publishing scientific instruments and laboratory software as standards-based network services. By automatically generating OpenAPI and WoT descriptions directly from Python implementations while providing lifecycle and concurrency semantics appropriate for physical hardware, it enables instruments to be exposed as interoperable, self-describing services with minimal additional software engineering effort.

# Software Design

`labthings-fastapi` represents units of hardware or software as subclasses of `Thing`. Properties and actions exposed by each Thing are defined using Python attributes, methods, type annotations, and decorators, allowing the implementation and network-facing description of the instrument to be maintained together. FastAPI and Pydantic use the type information to validate data and generate an OpenAPI description of the HTTP API, avoiding separate endpoint and schema definitions for much of the instrument interface.

The framework adopts concepts and vocabulary from the W3C Web of Things model [@wot-td]. Individual units of hardware or software are represented as Things, hardware state can be exposed through properties, and operations can be represented as actions. `labthings-fastapi` generates a Thing Description for each `Thing` alongside the OpenAPI description of its HTTP interface. The current implementation supports properties and actions but does not yet implement WoT events. The resulting OpenAPI and Thing Description documents provide complementary descriptions of the HTTP API and the higher-level capabilities of the instrument.

Hardware also imposes lifecycle and concurrency requirements that differ from many conventional web applications. `labthings-fastapi` creates each `Thing` once during the lifetime of a server and provides mechanisms for its start-up and shutdown. Actions invoked over HTTP and property access are run in threads, allowing `Thing` implementations to use synchronous Python code rather than requiring hardware-control code to be asynchronous. HTTP request handling uses an asynchronous event loop, separating concurrency in the web interface from the programming model presented to hardware developers.

This design reflects the characteristics of laboratory hardware, where device-control libraries are commonly synchronous and frequently interact with resources that must not be instantiated repeatedly. Executing Thing code within threads allows existing hardware-control software to be reused without requiring developers to adopt asynchronous programming techniques. At the same time, the asynchronous HTTP layer ensures that user interfaces and other clients remain responsive while long-running instrument operations are in progress.

`labthings-fastapi` builds on experience gained from `python-labthings`, the original implementation of the framework. The new implementation replaces Flask and Marshmallow with FastAPI and Pydantic. FastAPI removes much of the custom code previously required to generate an OpenAPI description, while Python type annotations replace separate Marshmallow schemas and endpoint classes for defining action inputs and outputs. The revised architecture also represents separate components as multiple Things rather than combining extensions into a single large Thing, simplifying the generation of their Thing Descriptions. The changes retain the original aim of making laboratory hardware available through standardised network interfaces while reducing duplication in the code required to define those interfaces.

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
