from __future__ import annotations
from typing import Optional, Union, Any
from pydantic.dataclasses import dataclass
from pydantic import BaseModel


class Form(BaseModel):
    href: str  # This should conform to anyURI
    op: Union[str, list[str]]
    contentType: str = "application/json"

class DataSchema(BaseModel):
    title: Optional[str]
    description: Optional[str] = None
    const: Optional[Any] = None
    default: Optional[Any] = None
    unit: Optional[str] = None
    type: Optional[str] = None
    readonly: bool = False
    writeonly: bool = False

class InteractionAffordance(BaseModel):
    title: Optional[str]
    forms: list[Form]
    description: Optional[str] = None

class PropertyAffordance(InteractionAffordance, DataSchema):
    observable: bool = False


class ThingDescription(BaseModel):
    properties: list[PropertyAffordance]
