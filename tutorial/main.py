from fastapi import FastAPI
from pydantic.decorator import _typing_extra  # See comments on its use below.
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Mapping, Optional, Tuple, Type, TypeVar, Union, overload
from inspect import Parameter, signature
from pydantic import BaseModel, create_model
import warnings

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}

from typing import Optional


@app.get("/items/{item_id}")
async def read_item(item_id: int, scaling_factor: float = 1.0):
    return {"item_id": item_id}

def anactionfunc(repeats: int, title: str="Untitled", attempts: Optional[list[str]] = None) -> str:
    return "finished!!"

#vf = ValidatedFunction(anactionfunc, config=None)

def model_from_signature(func):
    """Create a pydantic model for a function's signature.
    
    This is deliberately quite a lot more basic than 
    `pydantic.decorator.ValidatedFunction` because it is designed
    to handle JSON input. That means that we don't want positional 
    arguments, unless there's exactly one (in which case we have a
    single value, not an object, and this may or may not be supported).

    This will fail for position-only arguments, though that may change
    in the future.
    """
    # The code below is pinched from `pydantic.decorator.ValidatedFunction`.
    # The `type_hints` mapping is an internal pydantic fix-up that helps
    # with forward and backward compatibility. I will need to take care in
    # unit testing that this doesn't break in the future.
    parameters: Mapping[str, Parameter] = signature(func).parameters
    type_hints = _typing_extra.get_type_hints(func, include_extras=True)

    fields: Dict[str, Tuple[Any, Any]] = {}
    takes_kwargs = False
    
    for name, p in parameters.items():
        if p.annotation is p.empty:
            annotation = Any
        else:
            annotation = type_hints[name]

        default = ... if p.default is p.empty else p.default
        if name.startswith("__"):
            warnings.warn(
                f"{func.__name__} has an argument {name} that starts with __, "
                "which is not supported by model_from_signature and will be "
                "ignored"
            )
            continue
        if p.kind == Parameter.POSITIONAL_ONLY:
            raise ValueError(
                "model_from_signature cannot currently process functions "
                f"with positional only arguments. {function.__name__} has "
                "at least one such argument."
            )
        elif p.kind == Parameter.POSITIONAL_OR_KEYWORD:
            fields[name] = annotation, default
        elif p.kind == Parameter.KEYWORD_ONLY:
            fields[name] = annotation, default
        elif p.kind == Parameter.VAR_POSITIONAL:
            raise ValueError(
                "model_from_signature cannot currently cope with functions "
                "that accept a variable number of positional arguments."
                f"{function.__name__} has at least one such argument."
            )
        else:
            takes_kwargs = True
    
    name = f"{func.__name__}_input"

    class Config:
        extras = "allow" if takes_kwargs else "forbid"

    return create_model(name, **fields, __config__=Config)




@app.get("/anaction")
def _(body: vf.model):
     return anactionfunc(**body)