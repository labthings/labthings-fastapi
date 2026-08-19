---
name: Pull request
about: Proposed changes to the software.
title: ''
labels: ''
assignees: ''
---

**REPLACE ME** with a short summary of the context for this merge request.
<!-- Add summary of what this MR does above this comment -->

<!-- Closes #???-->
<!-- OFM-Feature-Branch: branchname -->

## This MR contains the following
* Bulleted
* Description of changes

<!-- uncomment if there are things to finish before merge
## Before merge:

* [ ] Remaining thing 1
* [ ] Remaining thing 2
-->


## Merge checklist:
<!-- Do not remove irrelevant checklist items.-->
<!-- Use ~strikeout~ to strike out not applicable questions, removing the [ ] so that the checklist count is correct.-->

* [ ] All new/changed functions have up to date typehints and docstrings.
* [ ] Any changes to the public API have been updated in `docs/src/public_api.rst`.
* [ ] New or changed features have been added to (or updated in) the conceptual documentation.
* [ ] Any new or updated dependencies have been added to the project configuration (e.g., `pyproject.toml`).
* [ ] New functionality is fully tested.
* [ ] Any decrease in test coverage has been justified.
* [ ] Either the `test-against-ofm-v3` job passes, or `test-against-ofm-feature-branch` passes.
* [ ] New features have been used in a branch of the OpenFlexure Microscope, which is tested in `test-against-ofm-feature-branch`.
      <!-- Note: uncomment the `OFM-Feature-Branch: branchname` line above to test against a feature branch in CI. -->
* [ ] This code has been tested manually against simulated hardware (detail tests in "Before merge").
* [ ] This code has been tested against real hardware (detail tests in "Before merge").

