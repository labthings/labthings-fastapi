from fastapi import FastAPI
from pydantic.decorator import ValidatedFunction
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Mapping, Optional, Tuple, Type, TypeVar, Union, overload

from ._internal import _typing_extra, _utils
from .config import Extra, get_config
from .decorators import validator
from .errors import PydanticUserError
from .main import BaseModel, create_model

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
    

@app.get("/anaction")
def _(body: vf.model):
     return anactionfunc(**body)