"""
A collection of utility functions to analyse types and metadata

Many parts of LabThings require us to use type annotations to
generate schemas/validation/documentation. This is done using
`pydantic` in keeping with the underlying FastAPI library.

This module collects together some utility functions that help
with a few key tasks, in particular creating pydantic models
from functions by analysing their signatures.
"""

from pydantic.decorator import ValidatedFunction, V_DUPLICATE_KWARGS
from typing import TYPE_CHECKING, Annotated, Any, Callable, Dict, List, Mapping, Optional, Tuple, Type, TypeVar, Union, overload
import inspect
from pydantic import BaseModel
import warnings


def vf_takes_v_args(vf: ValidatedFunction) -> bool:
    """Determine whether a ValidatedFunction accepts extra positional arguments
    
    There's no nice easy flag to check this, so we try the validator
    function, which should raise an exception if it doesn't accept
    variable numbers of positional arguments (i.e. if there's no `*args`).
    """
    try:
        vf.model.check_args([])
        # if check_args does not raise an exception, we accept a variable number
        # of positional arguments.
        return True

    except TypeError:
        # if an exception is raised, it means *args are not allowed
        return False

def vf_takes_v_kwargs(vf: ValidatedFunction) -> bool:
    """Determine whether a ValidatedFunction accepts extra keyword arguments
    
    There's no nice easy flag to check this, so we try the validator
    function, which should raise an exception if it doesn't accept
    extra keyword arguments (i.e. if there's no `**kwargs`).
    """
    try:
        vf.model.check_kwargs({})
        # if check_kwargs does not raise an exception, we accept a variable number
        # of positional arguments.
        return True

    except TypeError:
        # if an exception is raised, it means **kwargs are not allowed
        return False

def input_model_from_signature(
        func: callable, 
        ignore_positional_args: bool=False,
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
    * `ignore_positional_args`: By default, we will raise a `TypeError`
      if there are extra positional arguments (i.e. `*args`), but this 
      can be downgraded to a warning by specifying 
      `ignore_positional_args=True`.
    * `ignore_first_positional_arg`
    """
    vf = ValidatedFunction(func, None)
    model = vf.model

    # Raise errors if positional-only or variable positional args are present
    if vf_takes_v_args(vf):
        message = (
            f"{func.__name__} accepts extra positional arguments, "
            "which is not supported."
        )
        if ignore_positional_args:
            warnings.warn(message)
        else:
            raise TypeError(message)
    if len(vf.positional_only_args) > 0:
        raise TypeError(
            f"{func.__name__} has positional-only arguments which are not supported."
        )
    
    # Remove the extra fields used to trap and raise errors for 
    # the catch-all *args and **kwargs arguments.
    del model.__fields__[vf.v_args_name]
    del model.__fields__[vf.v_kwargs_name]
    del model.__fields__[V_DUPLICATE_KWARGS]

    if remove_first_positional_arg:
        del model.__fields__[vf.arg_mapping[0]]

    # If the function accepts extra kwargs, reflect that in the model
    model.Config.extras = "allow" if vf_takes_v_kwargs(vf) else "forbid"
    model.__name__ = f"{func.__name__}_input"
    return model


def return_type(func: Callable, name: Optional[str]=None) -> Type:
    """Determine the return type of a function."""
    sig = inspect.signature(func)
    if sig.return_annotation == inspect.Signature.empty:
        return type(None)
    else:
        return sig.return_annotation


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
    

