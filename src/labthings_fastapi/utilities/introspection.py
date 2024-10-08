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
from typing import Any, Callable, Dict, Optional, Sequence, Tuple, Type, get_type_hints
import inspect
from inspect import Parameter, signature
from pydantic import BaseModel, ConfigDict, Field, RootModel
from pydantic.main import create_model
from fastapi.dependencies.utils import analyze_param, get_typed_signature


class EmptyObject(BaseModel):
    model_config = ConfigDict(extra="allow")


class StrictEmptyObject(EmptyObject):
    model_config = ConfigDict(extra="forbid")


class EmptyInput(RootModel):
    root: Optional[EmptyObject] = None


class StrictEmptyInput(EmptyInput):
    root: Optional[StrictEmptyObject] = None


def input_model_from_signature(
    func: Callable,
    remove_first_positional_arg: bool = False,
    ignore: Optional[Sequence[str]] = None,
) -> type[BaseModel]:
    """Create a pydantic model for a function's signature.

    This is deliberately quite a lot more basic than
    `pydantic.decorator.ValidatedFunction` because it is designed
    to handle JSON input. That means that we don't want positional
    arguments, unless there's exactly one (in which case we have a
    single value, not an object, and this may or may not be supported).

    This will fail for position-only arguments, though that may change
    in the future.

    :param remove_first_positional_arg: Remove the first argument from the
        model (this is appropriate for methods, as the first argument,
        self, is baked in when it's called, but is present in the
        signature).
    :param ignore: Ignore arguments that have the specified name.
        This is useful for e.g. dependencies that are injected by LabThings.
    :returns: A pydantic model class describing the input parameters

    TODO: deal with (or exclude) functions with a single positional parameter
    """
    parameters: OrderedDict[str, Parameter] = OrderedDict(signature(func).parameters)
    if remove_first_positional_arg:
        name, parameter = next(iter((parameters.items())))  # get the first parameter
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
    takes_v_kwargs = False  # will be updated later
    # fields is a dictionary of tuples of (type, default) that defines the input model
    type_hints = get_type_hints(func, include_extras=True)
    fields: Dict[str, Tuple[type, Any]] = {}
    for name, p in parameters.items():
        if ignore and name in ignore:
            continue
        if p.kind == Parameter.VAR_KEYWORD:
            takes_v_kwargs = True  # we accept arbitrary extra arguments
            continue  # **kwargs should not appear in the schema
        # `type_hints` does more processing than p.annotation - but will
        # not have entries for missing annotations.
        p_type = Any if p.annotation is Parameter.empty else type_hints[name]
        # pydantic uses `...` to represent missing defaults (i.e. required params)
        default = Field(...) if p.default is Parameter.empty else p.default
        fields[name] = (p_type, default)
    model = create_model(  # type: ignore[call-overload]
        f"{func.__name__}_input",
        model_config=ConfigDict(extra="allow" if takes_v_kwargs else "forbid"),
        **fields,
    )
    # If there are no fields, we use a RootModel to allow none as well as {}
    if len(fields) == 0:
        return EmptyInput if takes_v_kwargs else StrictEmptyInput
    return model


def function_dependencies(
    func: Callable, dependency_types: Sequence[Type]
) -> Dict[str, tuple[type, type]]:
    """Determine whether a function's arguments require dependencies

    The return value maps argument names to a tuple of (type, full_type)
    where `full_type` is the annotation without simplification, i.e.
    it will include the contents of any Annotated objects.
    """
    type_hints = get_type_hints(func, include_extras=False)
    full_type_hints = get_type_hints(func, include_extras=True)
    return {
        name: (type_, full_type_hints[name])
        for name, type_ in type_hints.items()
        if type_ in dependency_types
    }


def fastapi_dependency_params(func: Callable) -> Sequence[Parameter]:
    """Find the arguments of a function that are FastAPI dependencies

    This allows us to "pass through" the full power of the FastAPI dependency
    injection system to thing actions.
    """
    # TODO: this currently ignores path parameters
    sig = get_typed_signature(func)
    dependencies = []
    for param_name, param in sig.parameters.items():
        param_details = analyze_param(
            param_name=param_name,
            annotation=param.annotation,
            value=param.default,
            is_path_param=False,
        )
        if param_details.depends is not None:
            dependencies.append(param)
    return dependencies


def return_type(func: Callable) -> Type:
    """Determine the return type of a function."""
    sig = inspect.signature(func)
    if sig.return_annotation == inspect.Signature.empty:
        return Any  # type: ignore[return-value]
    else:
        # We use `get_type_hints` rather than just `sig.return_annotation`
        # because it resolves forward references, etc.
        type_hints = get_type_hints(func, include_extras=True)
        return type_hints["return"]


def get_docstring(obj: Any, remove_summary=False) -> Optional[str]:
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


def get_summary(obj: Any) -> Optional[str]:
    """Return the first line of the dosctring of an object

    :param obj: Any Python object
    :returns: str: First line of object docstring

    """
    docs = get_docstring(obj)
    if docs:
        return docs.partition("\n")[0].strip()
    else:
        return None
