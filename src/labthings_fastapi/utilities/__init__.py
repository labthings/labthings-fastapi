"""Utility functions used by LabThings-FastAPI."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import FunctionType
from typing import Any, Dict, Generic, Iterable, Optional, TypeVar

from fastapi import Response
from pydantic import (
    BaseModel,
    Field,
    PydanticSchemaGenerationError,
    RootModel,
    ValidationError,
    create_model,
)
from pydantic_core import PydanticSerializationError

from labthings_fastapi.exceptions import (
    InvalidReturnValueError,
    UnserialisableTypeError,
    UnsupportedConstraintError,
)

from .introspection import EmptyObject

__all__ = [
    "class_attributes",
    "attributes",
    "RootModelWrapper",
    "model_to_dict",
]


def class_attributes(obj: Any) -> Iterable[tuple[str, Any]]:
    """List all the attributes of an object's class.

    This function gets all class attributes, including inherited ones.
    It is used to obtain the various descriptors used to represent
    properties and actions. It calls `.attributes` on ``obj.__class__``.

    :param obj: The instance, usually a `~lt.Thing` instance.

    :yield: tuples of ``(name, value)`` giving each attribute of the class.
    """
    cls = obj.__class__
    yield from attributes(cls)


def attributes(cls: Any) -> Iterable[tuple[str, Any]]:
    """List all the attributes of an object not starting with `__`.

    :param cls: The object whose attributes we are listing. This may be
        a class, because classes are objects too.

    :yield: tuples of ``(name, value)`` giving each attribute and its
        value.
    """
    for name in dir(cls):
        if name.startswith("__"):
            continue
        yield name, getattr(cls, name)


WrappedT = TypeVar("WrappedT")


class RootModelWrapper(RootModel[WrappedT], Generic[WrappedT]):
    """A RootModel subclass for automatically-wrapped types.

    There are several places where LabThings needs a model, but may only
    have a plain Python type. This subclass indicates to LabThings that
    a type has been automatically wrapped, and will need to be unwrapped
    in order for the value to have the correct type.

    It also provides methods to automatically wrap types if they are not
    already `pydantic.BaseModel` subclasses, and to unwrap them again.
    """

    @classmethod
    def wrap_type(
        cls,
        model: type,
        constraints: Mapping[str, Any] | None = None,
        name: str | None = None,
    ) -> type[BaseModel]:
        r"""Ensure a type is a subclass of BaseModel.

        If a `pydantic.BaseModel` subclass is passed to this function, we will pass it
        through unchanged. Otherwise, we wrap the type in a `pydantic.RootModel`.
        In the future, we may explicitly check that the argument is a type
        and not a model instance.

        :param model: A Python type or `pydantic` model.
        :param constraints: is passed as keyword arguments to `pydantic.Field`
            to add validation constraints to the property.
        :param name: the name to use for the dynamically created model.

        :return: A `pydantic` model, wrapping Python types in a ``RootModel`` if needed.

        :raises UnsupportedConstraintError: if constraints are provided for an
            unsuitable type, for example `allow_inf_nan` for an `int` property, or
            any constraints for a `BaseModel` subclass.
        :raises UnserialisableTypeError: if the type being wrapped is not able
            to be serialised by `pydantic`\ .
        :raises RuntimeError: if other errors prevent Pydantic from creating a schema
            for the generated model.
        """
        try:  # This needs to be a `try` as basic types are not classes
            if issubclass(model, BaseModel):
                if constraints:
                    raise UnsupportedConstraintError(
                        "Constraints may only be applied to plain types, not Models."
                    )
                return model
        except TypeError:
            pass  # some types aren't classes and that's OK - they still get wrapped.
        constraints = constraints or {}
        try:
            # Dynamically create a subclass of RootModelWrapper for the supplied type.
            return create_model(
                f"{name or cls.__name__}[{model!r}]",
                root=(model, Field(**constraints)),
                __base__=cls,
            )
        except PydanticSchemaGenerationError as e:
            raise UnserialisableTypeError(
                f"LabThings does not know how to serialise {model!r} to JSON."
            ) from e
        except RuntimeError as e:
            if "Unable to apply constraint" in str(e):
                raise UnsupportedConstraintError(str(e)) from e
            raise e

    @classmethod
    def unwrap(cls, value: BaseModel | None) -> Any:
        r"""If the supplied value is a `RootModelWrapper`, unwrap it.

        :param value: a model instance.
        :return: the root value, if ``value`` is a `RootModelWrapper`\ , or ``value``
            if not.
        """
        if value is None:
            return None
        if isinstance(value, cls):
            return value.root
        return value


def refer_to_user_code(
    code: Callable | tuple[type, str] | None = None, suffix: str = "\n"
) -> str:
    r"""Refer to a user-supplied function or property.

    This function generates a human-readable error string that should enable someone
    to find a problem in downstream code.

    If `code` is `None` the empty string will be returned. This is intended to simplify
    the construction of error messages that may or may not include a code location.

    :param code: the code that generated `value`\ . This may be either a function,
        a tuple consisting of a class and an attribute name, or a string (which
        should describe how to find the user code that generated the value).
    :param suffix: a string that terminates the message, by default a newline. This
        is not used if `code` is None, and instead the empty string is returned.
    :return: a string referring to the user code, for use in an error message, or
        the empty string if no user code is specified.
    """
    if callable(code):
        if isinstance(code, FunctionType):
            # As a rule, we'll pass a function and this code works.
            co = code.__code__
            return (
                f"This value was returned by '{co.co_name}' "
                f"at {co.co_filename}:{co.co_firstlineno}.{suffix}"
            )
        else:
            # As a fallback (not currently used), just dump the object to string.
            return f"This value was returned by {repr(code)}.{suffix}"
    elif isinstance(code, tuple) and len(code) == 2:
        cls, attr = code
        return (
            "You may want to check the definition of "
            f"{cls.__module__}.{cls.__qualname__}.{attr}.{suffix}"
        )
    else:
        return ""


ModelT = TypeVar("ModelT", bound=BaseModel)


def validate_from_user_code(
    model: type[ModelT],
    value: Any,
    description: str,
    code: Callable | tuple[type, str] | None = None,
) -> ModelT:
    r"""Validate a return value from user code, with error handling.

    This wraps ``return model.model_validate(value)`` in error handling code.
    It is intended to help LabThings generate better errors when models fail
    to validate, in particular making clear where in the user's code the value
    was generated, and why it didn't validate.

    :param model: the `pydantic` model to use for validation.
    :param value: the value passed to ``model.model_validate()``\ .
    :param description: a description of the value, e.g. "the output of {action}".
    :param code: the code that generated `value`\ .
        This will be passed to `refer_to_user_code` - see that function for details.

    :return: a validated model instance.
    :raises InvalidReturnValueError: if the model failed to validate.
    """
    try:
        return model.model_validate(value)
    except ValidationError as e:
        msg = (
            f"Error validating {description} against its model.\n"
            f"The value was '{value}' and the model was {model}.\n"
            f"{refer_to_user_code(code)}"
            f"The validation error was:\n{e}\n"
        )
        raise InvalidReturnValueError(msg) from e


def serialise_from_user_code(
    model_instance: BaseModel,
    description: str,
    status_code: int = 200,
    code: Callable | tuple[type, str] | None = None,
) -> Response:
    r"""Return a value from a model instance, with appropriate error handling.

    This function implements very similar logic to FastAPI's default behaviour when
    an endpoint function is typed as returning a `pydantic.BaseModel` instance.
    The validated model instance is serialised to JSON by calling
    ``model_dump_json()`` on the model instance, and the resulting string is returned
    in a `Response` object. This uses `pydantic` serialisation, written in Rust,
    and outperforms the native `json` library significantly.

    If the model can't be serialised, we raise an exception with information about
    the place in the user code where the problem occurred.

    :param model_instance: the `pydantic` model to use for validation.
    :param description: a description of the value, e.g. "the output of {action}".
    :param status_code: an HTTP status code to use.
    :param code: the code that generated `value`\ .
        This will be passed to `refer_to_user_code` - see that function for details.
    :return: a `fastapi.Response` object containing a 200 code and the serialised
        value or a 500 code and the error message.
    :raises InvalidReturnValueError: if the model can't be serialised.
    """
    try:
        return Response(
            content=model_instance.model_dump_json(),
            status_code=status_code,
            media_type="application/json",
        )
    except PydanticSerializationError as exc:
        msg = (
            f"Error serialising {description} to JSON.\n"
            f"The value was validated as {repr(model_instance)}.\n"
            f"The serialisation error was '{exc}'.\n"
            f"{refer_to_user_code(code)}"
        )
        raise InvalidReturnValueError(msg) from exc


def model_to_dict(model: Optional[BaseModel]) -> Dict[str, Any]:
    """Convert a pydantic model to a dictionary, non-recursively.

    We convert only the top level model, i.e. we do not recurse into submodels.
    This is important to avoid serialising Blob objects in action inputs.
    This function returns `dict(model)`, with exceptions for the case of `None`
    (converted to an empty dictionary) and `pydantic.RootModel` (checked to see
    if they correspond to empty input).

    If `pydantic.RootModel` with non-empty input is allowed, this function will
    need to be updated to handle them.

    :param model: A Pydantic model (usually the input of an action).

    :return: A dictionary with string keys, which are the fields of the model.
        This should be suitable for using as ``**kwargs`` to an action.

    :raise ValueError: if we are given a root model that isn't empty.
    """
    if model is None:
        return {}
    if isinstance(model, RootModel):
        if model.root is None:
            return {}
        if isinstance(model.root, EmptyObject):
            return {}
        raise ValueError("RootModels with non-empty input are not supported")
    return dict(model)
