from typing import Any

def class_attributes(obj: Any) -> iter:
    """A list of all the attributes of an object's class"""
    cls = obj.__class__
    for name in dir(cls):
        yield getattr(cls, name)
