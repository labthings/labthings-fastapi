# JOSS Readiness Checklist for labthings-fastapi

## Documentation (Currently on ReadTheDocs)
JOSS requires clear documentation that allows a new user to understand and use the software.

- [x] Verify Installation Instructions: Ensure the pip install instructions are clear and account for any system-level dependencies.
    - [x] Add additional instructions for Windows specific installation as there are additional requirements (MR #367)

- [ ] Usage Examples / Tutorials: Reviewers need to see examples of how to use the software to solve real-world problems. Ensure the ReadTheDocs includes a clear, executable example of spinning up a Thing and interacting with it.

- [ ] API Reference: Confirm that the top-level API summary (lt.*) and Pydantic models are fully rendered and easily navigable.

- [ ] W3C Web of Things (WoT) Context: Clearly document how the framework implements or extends the WoT specification (this will tie directly into the paper).

- [ ] Consider renaming the project to 'labthings'

## Testing & Continuous Integration (CI)
JOSS reviewers will look closely at the testing framework to ensure the software is reliable.

- [ ] Test Coverage: We already have pytest, mypy, ruff, and codecov running via GitHub Actions. Check the Codecov reports to ensure you have high coverage of the core logic, particularly the FastAPI routing and hardware interfacing. (MR #368)

- [ ] Local Test Instructions: Ensure there are clear instructions for reviewers to run the test suite locally (e.g., pytest tests/). (MR #368)

- [ ] Create PR merge checklist and release checklist (as well as making them in GitHub templates, I may also add them to contributing.md once #367 is merged)

## Community & Repository Health
JOSS requires evidence of open development practices and a welcoming environment for external contributors.

- [x] Add a CONTRIBUTING.md file: We currently have "Developer notes" in the README, but JOSS strongly prefers a dedicated CONTRIBUTING.md file outlining how users can submit issues, run tests, and open pull requests. This file should include how to: (MR #367)
    - [x] Contribute to the software (code/docs). (MR #367)
    - [x] Report issues or bugs. (MR #367)
    - [x] Seek support. (MR #367)

- [ ] Verify Issue Tracker Activity: JOSS requires evidence of iterative development over time. With over 1,000 commits over the last 3 years and active PRs/Issues, we should easily pass this gate.

- [x] Check License: We have an MIT license, which fulfills the OSI-approved license requirement.

## Paper Generation
See an example at:https://joss.readthedocs.io/en/latest/example_paper.html

- [ ] Draft paper.md: Create the JOSS-formatted paper in the root of your repository (see [paper.md](./paper.md)).

- [ ] Compile paper.bib: Gather all necessary BibTeX references (e.g., the W3C WoT spec, FastAPI, OpenFlexure Microscope papers).

- [ ] Automated Paper Check: Once drafted, you can use the JOSS editorial bot to generate a PDF preview of your paper directly from your GitHub repository to ensure the metadata parses correctly.
