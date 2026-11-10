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

## AI Contributions
<!-- You must disclose your use of AI in this contribution. -->

 <!-- delete or add lines below as applicable -->
AI has been used as part of this pull request to:
* Assist in debugging or research (no need to include in commit messages).
* Generate code in the Python library (must disclose in a commit message).
* Generate code in the test suite (must disclose in a commit message).
* Generate ancillary code for CI/tooling (must disclose in a commit message).
AI was not used as part of this pull request.

AI tools used as part of this pull request were:
* Please detail the tool and model used.

<!-- Use ~strikeout~ to strike out not applicable questions, removing the [ ] so that the checklist count is correct.-->
* [ ] This Pull Request description has been written by a human. <!-- this is always required -->
* [ ] Any AI-generated code has been fully reviewed by a human.
* [ ] Any AI-generated code is documented in commit messages.
* [ ] I (the pull request creator) have the authority to release this contribution under the project's license (MIT). <!-- do not delete this line -->

If your AI use is not documented in commit messages, please rewrite your commit messages to include this. If that's impossible, leave the checkbox empty: whoever merges this should include an AI use statement in the merge commit.

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

