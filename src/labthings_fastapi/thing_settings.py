"""
Settings management for things

ThingSettings is a dictionary-like object that manages settings for one Thing
"""

from __future__ import annotations
import json
import os
import os.path
from collections.abc import Mapping
from typing import Any, Callable, Optional
from weakref import WeakSet


class ReactiveDict(Mapping):
    def __init__(
        self,
        data: Optional[Mapping] = None,
        name: Optional[str] = None,
        callback: Optional[Callable] = None,
    ):
        self.name = name if name is not None else ""
        self.callbacks: WeakSet[Callable] = WeakSet()
        self._data: dict[Any, Any] = {}
        if data:
            self.replace(data)
        if callback:
            self.callbacks.add(callback)

    def __getitem__(self, key):
        return self._data[key]

    def notify_callbacks(self, path=None):
        for c in self.callbacks:
            c(self, path)

    def child_callback(self, child: ReactiveDict, path: Any = None):
        """Propagate updates from children up to the parent object"""
        built_path = child.name
        if path:
            built_path += f"/{path}"
        self.notify_callbacks(path=built_path)

    def __setitem__(self, key, item):
        self._data[key] = item
        self.notify_callbacks(path=key)

    def __delitem__(self, key):
        del self._data[key]
        self.notify_callbacks(path=key)

    def __iter__(self):
        for k in self._data.keys():
            yield k

    def __len__(self):
        return len(self._data)

    def update(self, data: Mapping):
        """Update many key-value pairs at once"""
        if not isinstance(data, Mapping):
            raise ValueError("Config files must be Objects (key-value mappings)")
        for k, v in data.items():
            if isinstance(v, Mapping):
                self._data[k] = ReactiveDict(
                    v, name=f"{k}", callback=self.child_callback
                )
            else:
                self._data[k] = v
        self.notify_callbacks()

    def replace(self, data: Mapping):
        """Erase all data, then update from the supplied mapping"""
        self._data = {}
        self.update(data=data)

    @property
    def dict(self):
        """Return a regular, non-reactive dict of the data"""
        out = self._data.copy()
        for k, v in self._data.items():
            if isinstance(v, ReactiveDict):
                out[k] = v.dict
        return out


class ThingSettings(ReactiveDict):
    def __init__(self, filename: str):
        self.filename = filename
        if os.path.exists(filename):
            with open(filename, "r") as f:
                contents = json.load(f)
        else:
            contents = {}
        ReactiveDict.__init__(self, contents, callback=self.write_to_file)

    def write_to_file(self, *args, **kwargs):
        """Persist the dictionary to a file"""
        with open(self.filename, "w") as f:
            json.dump(self.dict, f, indent=4)
