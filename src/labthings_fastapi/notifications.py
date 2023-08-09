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
"""


from __future__ import annotations
import datetime
import logging
import traceback
from collections import deque
from enum import Enum
from threading import Event, Thread, Lock, get_ident
from typing import Optional, Callable, Iterable, Any, TypeVar, Generic
import uuid
from typing import TYPE_CHECKING
import weakref
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Request

class Listener():
