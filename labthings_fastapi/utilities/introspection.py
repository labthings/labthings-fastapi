"""
A collection of utility functions to analyse types and metadata

Many parts of LabThings require us to use type annotations to
generate schemas/validation/documentation. This is done using
`pydantic` in keeping with the underlying FastAPI library.

This module collects together some utility functions that help
with a few key tasks, in particular creating pydantic models
from functions by analysing their signatures.
"""

from collections import OrderedDict
from typing import (
    Any, Callable, Dict, List, Mapping, Optional, Tuple, Type, get_type_hints
)
import inspect
from inspect import Parameter, signature
from pydantic import BaseModel, ConfigDict
from pydantic.main import create_model


def input_model_from_signature(
        func: callable,
        remove_first_positional_arg: bool=False,
    ) -> BaseModel:
    """Create a pydantic model for a function's signature.
    
    This is deliberately quite a lot more basic than 
    `pydantic.decorator.ValidatedFunction` because it is designed
    to handle JSON input. That means that we don't want positional 
    arguments, unless there's exactly one (in which case we have a
    single value, not an object, and this may or may not be supported).

    This will fail for position-only arguments, though that may change
    in the future. 
    
    Parameters:
    * `remove_first_positional_arg` removes the first argument from the 
      model (this is appropriate for methods, as the first argument, 
      self, is baked in when it's called, but is present in the 
      signature).

    TODO: stop relying on ValidatedFunction.model and build it directly.
    This isn't actually much code: ValidatedFunction is mostly concerned
    with replicating the exact Python arguments, and we don't care (we
    only want to allow keyword arguments anyway).
    TODO: deal with (or exclude) functions with a single positional parameter
    """
    parameters: OrderedDict[str, Parameter] = OrderedDict(signature(func).parameters)
    if remove_first_positional_arg:
        name, parameter = next(iter((parameters.items())))  # next(iter()) gets the first item
        if parameter.kind in (Parameter.KEYWORD_ONLY, Parameter.VAR_KEYWORD):
            raise ValueError("Can't remove first positional argument: there is none.")
        del parameters[name]

    # Raise errors if positional-only or variable positional args are present
    if any(p.kind == Parameter.VAR_POSITIONAL for p in parameters.values()):
        raise TypeError(
            f"{func.__name__} accepts extra positional arguments, "
            "which is not supported."
        )
    if any(p.kind == Parameter.POSITIONAL_ONLY for p in parameters.values()):
        raise TypeError(
            f"{func.__name__} has positional-only arguments which are not supported."
        )
    
    # The line below determines if we accept arbitrary extra parameters (**kwargs)
    takes_v_kwargs = any(p.kind == Parameter.VAR_KEYWORD for p in parameters.values())
    # fields is a dictionary of tuples of (type, default) that defines the input model
    type_hints = get_type_hints(func, include_extras=True)
    fields: Dict[str, Tuple[type, Any]] = {}
    for name, p in parameters.items():
        p_type = Any if p.annotation is Parameter.empty else type_hints[name]
        default = ... if p.default is Parameter.empty else p.default  # convert Parameter.empty to `...`
        fields[name] = (p_type, default)
    model = create_model(
        f"{func.__name__}_input",
        __config__ = ConfigDict(extra="allow" if takes_v_kwargs else "forbid"),
        **fields
    )

    print(f"Extracted model from function arguments:\nname: {model.__name__}\nfields:{model.__fields__}")
    return model


def return_type(func: Callable, name: Optional[str]=None) -> Type:
    """Determine the return type of a function."""
    sig = inspect.signature(func)
    if sig.return_annotation == inspect.Signature.empty:
        return type(None)
    else:
        # We use `get_type_hints` rather than just `sig.return_annotation`
        # because it resolves forward references, removes annotations, etc.
        type_hints = get_type_hints(func, include_extras=True)
        return type_hints["return"]


def get_docstring(obj: Any, remove_summary=False) -> str:
    """Return the docstring of an object

    If `remove_newlines` is `True` (default), newlines are removed from the string.
    If `remove_summary` is `True` (not default), and the docstring's second line
    is blank, the first two lines are removed.  If the docstring follows the
    convention of a one-line summary, a blank line, and a description, this will
    get just the description.

    If `remove_newlines` is `False`, the docstring is processed by
    `inspect.cleandoc()` to remove whitespace from the start of each line.

    :param obj: Any Python object
    :param remove_newlines: bool (Default value = True)
    :param remove_summary: bool (Default value = False)
    :returns: str: Object docstring

    """
    ds = obj.__doc__
    if not ds:
        return None
    if remove_summary:
        lines = ds.splitlines()
        if len(lines) > 2 and lines[1].strip() == "":
            ds = "\n".join(lines[2:])
    return inspect.cleandoc(ds)  # Strip spurious indentation/newlines


def get_summary(obj: Any) -> str:
    """Return the first line of the dosctring of an object

    :param obj: Any Python object
    :returns: str: First line of object docstring

    """
    docs = get_docstring(obj)
    if docs:
        return docs.partition("\n")[0].strip()
    else:
        return None
    

