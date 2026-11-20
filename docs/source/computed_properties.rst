.. _computed_properties:

Computed Properties
=========================

Computed properties are a special class of functional properties that depend only on the value of other properties. LabThings automatically tracks which other properties they depend on. This means the computed property will be automatically recalculated whenever one of those properties changes. An important consequence of this is that computed properties are *observable*. That means it's possible to subscribe to notifications of when the computed property changes, for example using a websocket.

In order for computed properties to work, some care is needed to write them such that they *only* depend on other properties of the Thing. All of the properties that a computed property depends on must be observable, which usually means they are either data properties or other computed properties.

Computed properties can be useful in a variety of places - for example, providing a composite property that includes the values of several individual properties or settings, or checking that a validation criterion is met. For example, consider a Thing that has a few settings:

.. code-block:: python

    import labthings_fastapi as lt


    class Scanner(lt.Thing):
        scan_points: int = lt.setting(default=10)
        vector_a: tuple[float, float] = lt.setting(default=(1, 0))
        vector_b: tuple[float, float] = lt.setting(default=(0, 1))

        @lt.computed_property
        def all_settings(self) -> dict:
            """A quick way to get all the scan settings."""
            return {
                "scan_points": self.scan_points,
                "vector_a": self.vector_a,
                "vector_b": self.vector_b,
            }
        
        @lt.computed_property
        def settings_valid(self) -> bool:
            """Whether the current settings would work.
            
            This can't be a validator on any one setting, because
            it depends on all of them.
            """
            a = self.vector_a
            b = self.vector_b
            if a[0]*b[1] + a[1]*b[0] == 0 or self.scan_points == 1:
                return True
            else:
                return False


A structure like this would allow a client to set each of the settings individually, and receive websocket notifications that tell it when the settings are OK, and when they are not valid. That's more efficient and easier to code than polling each time something is changed. A client that observes ``all_settings`` will get an update any time a setting changes, and that update will include all three values in a dictionary.


Setting computed properties
---------------------------

Computed properties may have setters. LabThings doesn't place any restrictions on what they can do, though it's almost always the case that they will only change the values of properties that are used in the getter. A trivial example would be two properties that are required to add up to the same total:

.. code-block:: python

    import labthings_fastapi as lt

    class FractionThing(lt.Thing):
        """The two properties of this Thing must always add up to 1."""

        p: float = lt.property(default=0)
        """This must always satisfy p+q==1."""

        @lt.computed_property
        def q(self) -> float:
            """One minus p."""
            return 1-self.p
        
        @q.setter
        def _set_q(self, value: float) -> None:
            """Change p such that q takes this value."""
            self.p = 1 - value

If ``p`` is changed, ``q`` will be automatically recomputed. If ``q`` is changed, it will change ``p`` such that ``q`` takes the intended value. Note that we can't set ``q`` directly - the only way to change its value is to change the properties it depends on.

Manually recomputing and publishing
-----------------------------------

It is possible to trigger an update message about any property in LabThings, by calling ``thing.properties["name"].publish()``. On data or functional properties, this simply gets the property's value and broadcasts it to any observers. If called on a computed property, it will trigger a recomputation of that property. It shouldn't be necessary to do this most of the time, as it ought to recompute automatically. However, it's sometimes possible to get into a situation (e.g. using mutable values) where the value has changed without LabThings triggering a notification. In these situations, calling ``publish()`` will get everything back in sync.

Concurrency considerations
--------------------------

.. info::
    
    This section is intended for developers.

Computed properties rely on the `MessageBroker` mechanism that is used by websockets. As such, the signals that cause them to recompute their value come via the event loop. The computation is performed in a worker thread to minimise the risk that user code ends up blocking the event loop, and to avoid having to think about coroutines when writing what should be a very simple function. This does, however, lead to a slightly awkward structure. The following sequence illustrates how a computed property is implemented.

* LabThings starts up, and calls ``__enter__`` on each of the `~lt.Thing`\ s.
* LabThings starts a coroutine for each computed property (`ComputedProperty._watch_for_changes`).
    - The coroutine recomputes the property by running the getter in a worker thread.
        - Each time the getter accesses a property, it calls back to the event loop and subscribes to that property.
    - The coroutine recomputes in a worker thread every time the property changes.

This slightly complicated structure ensures that we are always subscribed to changes before we access the value of a property, avoiding the risk that we miss updates to properties that happen while the recomputation is running.

Infinite loops and recursion
----------------------------

If two computed properties depend on each other, if either one is accessed we will end up with an infinite loop and a recursion error. This is no different from what would happen with two regular properties outside of LabThings, and will result in exactly the same `RecursionError`.

If the getter for a computed property has side effects, there's the potential for strange behaviour. Access to `self` from the getter function is therefore restricted only to reading other observable properties, which minimises the likelihood of strange things happening.
