"""
Handle notification of events, property, and action status changes

There are several kinds of "event" in the WoT vocabulary, not all of which
are called Event, which is why this module is called `notifications`.
In all cases, these are events that happen on an exposed Thing, and
may need to be relayed to one or more listeners (currently via a
WebSocket connection, though long polling may also be an option in the
future).

The aim at this stage (July 2023) is for a minimal working example that
enables property changes to be fed via a websocket. Events proper should
not be a big step thereafter.

Currently, this code is more or less all in `websockets.py` and
`descriptors/property.py` but it should get consolidated.
"""

from __future__ import annotations


class Listener:
    pass
