"""A collection of utility functions to analyse types and metadata.

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
    """A model representing an object with no required keys."""

    model_config = ConfigDict(extra="allow")


class StrictEmptyObject(EmptyObject):
    """A model representing an object that must have no keys."""

    model_config = ConfigDict(extra="forbid")


class EmptyInput(RootModel):
    """Represent the input of an action that has no required parameters.

    This may be either a dictionary or ``None``.
    """

    root: Optional[EmptyObject] = None


class StrictEmptyInput(EmptyInput):
    """Represent the input of an action that never takes parameters.

    This may be either an empty dictionary or ``None``.
    """

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
    arguments.

    .. note::

        LabThings-FastAPI does not currently support actions that take
        positional arguments, because this does not convert nicely into
        JSONSchema or Thing Description documents (see wot_td_).

    :param func: the function to analyse.
    :param remove_first_positional_arg: Remove the first argument from the
        model (this is appropriate for methods, as the first argument,
        self, is baked in when it's called, but is present in the
        signature).
    :param ignore: Ignore arguments that have the specified name.
        This is useful for e.g. dependencies that are injected by LabThings.

    :return: A pydantic model class describing the input parameters

    :raise TypeError: if positional arguments are used: this is not supported.
    :raise ValueError: if ``remove_first_positional_arg`` is true but there
        is no initial positional argument.
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
        # p_type below has a complicated type, but it is reasonable to
        # call p_type a `type` and ignore the mypy error.
        fields[name] = (p_type, default)  # type: ignore[assignment]
    model = create_model(  # type: ignore[call-overload]
        f"{func.__name__}_input",
        model_config=ConfigDict(extra="allow" if takes_v_kwargs else "forbid"),
        **fields,
    )
    # If there are no fields, we use a RootModel to allow none as well as {}
    if len(fields) == 0:
        return EmptyInput if takes_v_kwargs else StrictEmptyInput
    return model


def fastapi_dependency_params(func: Callable) -> Sequence[Parameter]:
    """Find the arguments of a function that are FastAPI dependencies.

    This allows us to "pass through" the full power of the FastAPI dependency
    injection system to thing actions. Any function parameter that has a
    type hint annotated with `fastapi.Depends` will be treated as a
    dependency, and thus be supplied automatically when it is called over
    HTTP. See dependencies_ for an overview.

    We give special treatment to dependency parameters, as they must not
    appear in the input model, and they must be supplied by the
    `.DirectThingClient` wrapper to make the signature identical to that
    of the `.ThingClient` over HTTP.

    .. note::

        Path and query parameters are ignored. These should not be used as action
        parameters, and will most likely raise an error when the `.Thing` is
        added to FastAPI.

    :param func: a function to inspect.

    :return: a list of parameter objects that are annotated as dependencies.
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
    """Determine the return type of a function.

    :param func: a function to inspect

    :return: the return type of the function.
    """
    sig = inspect.signature(func)
    if sig.return_annotation == inspect.Signature.empty:
        return Any  # type: ignore[return-value]
    else:
        # We use `get_type_hints` rather than just `sig.return_annotation`
        # because it resolves forward references, etc.
        type_hints = get_type_hints(func, include_extras=True)
        return type_hints["return"]


def get_docstring(obj: Any, remove_summary: bool = False) -> Optional[str]:
    """Return the docstring of an object.

    Get the docstring of an object, optionally removing the initial "summary"
    line.

    If `remove_summary` is `True` (not default), and the docstring's second line
    is blank, the first two lines are removed.  If the docstring follows the
    convention of a one-line summary, a blank line, and a description, this will
    get just the description.

    The docstring is processed by
    `inspect.cleandoc()` to remove whitespace from the start of each line.

    :param obj: Any Python object.
    :param remove_summary: whether to remove the summary line, if present.
    :returns: str: The object's docstring.

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
    """Return the first line of the dosctring of an object.

    :param obj: Any Python object
    :returns: str: First line of object docstring, or ``None``.

    """
    docs = get_docstring(obj)
    if docs:
        return docs.partition("\n")[0].strip()
    else:
        return None
