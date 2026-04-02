.. _optional_features:

Optional Features and updates
=============================

LabThings allows some features to be turned on and off globally, using the `lt.FEATURE_FLAGS` object.
This was introduced as a way to smooth the upgrade process for downstream projects, meaning that when a new version of LabThings is released, they need not adopt all the new features at once.

Typically, your application will set the feature flags once, just after importing LabThings. For example, to validate properties when they are written to in Python, we would do:

.. code-block: python

    import labthings_fastapi as lt


    lt.FEATURE_FLAGS.validate_properties_on_set = True

When new features are intended to become non-optional, the usual procedure will be:

* Introduce the feature in a release, but disable it by default. It may be activated by setting a flag to `True`\ .
* At some point (either the release that introduces it, or a future release) a `DeprecationWarning` will be raised by relevant code if the feature has not been enabled.
* A subsequent release will enable the feature by default, but it may still be disabled by setting the flag to `False`\ . This will raise a `DeprecationWarning`\ .
* Another release will remove the feature flag and the feature will be permanently enabled.

Introducing a feature that's disabled by default, and adding `DeprecationWarning`\ s, are not "breaking changes" as they require no change to downstream code.
Enabling a feature by default, or removing the ability to disable a feature, would constitute a "breaking change".
While our major version is zero, the intention is that patch releases (e.g. ```0.1.0``` to ``0.1.1``) should not make breaking changes, but minor releases (e.g. ``0.1.0`` to ``0.2.0``) may do so.
After `v1.0.0` LabThings should follow the Semantic Versioning convention and make breaking changes only when the major version changes.