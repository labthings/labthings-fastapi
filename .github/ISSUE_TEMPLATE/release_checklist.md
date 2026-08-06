---
name: Release checklist
about: Ensure the project is ready to make a release.
title: Release Checklist v?.?.?
labels: ''
assignees: ''

---

*This release checklist is intended to help keep to a consistent process for minor version releases.*
*The same process may be used for point releases, though usually with compressed timescales.*

*Minor version releases will generally be made from the `main` branch.*
*Bugfix releases may be made either from `main` or from a protected `v0.x` branch depending on whether there are significant changes already merged onto `main`.*

**Start of cycle**
- [ ] Create a milestone for the release.
- Add issues and pull requests to the release.

**Development**
- Open pull requests to close issues, prioritising those tagged for the next release.
- Periodically review priorities, usually with a subset of the OpenFlexure team.

**Release preparation**
- [ ] Decide on issues and PRs that will be included, adjusting milestones as necessary.
- [ ] Make a prerelease on PyPI for testing.

**Manual testing**
- [ ] Ensure the prerelease is tested against a real system (currently this will be an OpenFlexure Microscope).
- [ ] Open issues and PRs to fix any bugs that are found.

**Release**
- [ ] Bump the version number.
- [ ] Make a release on Github, including a changelog in the release notes.
- [ ] Verify that the release appears on PyPI and add a link to the Github release.
