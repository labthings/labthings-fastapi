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
    affiliation: "1, 2" # (Multiple affiliations must be quoted)
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
### Beth

[1-2 paragraphs for a general audience]
Describe what `labthings-fastapi` is. Explain that it is a ground-up rewrite of the original `python-labthings`, leveraging modern Python asynchronous capabilities via FastAPI and data validation via Pydantic. Briefly state its primary function: allowing laboratory hardware (such as microscopes or sensors) to be exposed over a network in a standardised way.

# Statement of need
### Beth

[2-3 paragraphs for your target audience]
Describe the specific problem `labthings-fastapi` solves in the research community. 
* Why is exposing lab hardware over a network difficult? 
* Who is the target audience? (e.g., researchers building custom lab equipment, developers of the OpenFlexure Microscope).
* How does it compare to other laboratory automation frameworks (if any exist in this specific niche)? 

# State of the field
### Beth/Richard

[1-2 paragraphs for your target audience]
Describe existing tools for Web of Things, and any tools specific to hardware or laboratory hardware.
* Explain why `labthings-fastapi` was created instead of contributing to existing work
* Explain the gaps in the field closed by `labthings-fastapi`

# Software Design
### Richard/Joel/Julian

[1-2 paragraphs detailing the Implementation and the Web of Things Specification/architecture]
Detail how `labthings-fastapi` relates to the W3C Web of Things (WoT) Thing Description specification. 
* Explain how the framework maps Python objects and hardware states to the WoT JSON-LD formats.
* Briefly mention the advantages of using FastAPI (e.g., automatic OpenAPI documentation, asynchronous performance) for this specific application.

# Research impact statement
### Ben/Joe/Richard

[1-3 paragraphs describing the impact `labthings-fastapi` has had on research]
* Use in OpenFlexure Microscope
* Microscope Farm case study

# AI Usage Disclosure
No AI tools were used in the creation of this software, documentation, or paper.

# Acknowledgements

We acknowledge contributions from [Name] during the early development of this project, and funding from [Grant Name/Number] which supported this work.

# References