"""Load objects from object references."""

import importlib
from typing import Any


def object_reference_to_object(object_reference: str) -> Any:
    """Convert a string reference to an object.

    This is taken from:
    https://packaging.python.org/en/latest/specifications/entry-points/

    The format of the string is `module_name:qualname` where `qualname`
    is the fully qualified name of the object within the module. This is
    the same format used by entrypoints` in `setup.py` files.

    :param object_reference: a string referencing a Python object to import.

    :return: the Python object.

    :raise ImportError: if the referenced object cannot be found or imported.
    """
    modname, qualname_separator, qualname = object_reference.partition(":")
    obj = importlib.import_module(modname)
    if qualname_separator:
        for attr in qualname.split("."):
            try:
                obj = getattr(obj, attr)
            except AttributeError:
                raise ImportError(
                    f"Cannot import name {attr} from {obj} "
                    f"when loading '{object_reference}'"
                )
    return obj
