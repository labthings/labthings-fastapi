from __future__ import annotations
from typing import Optional, Union, Any
from pydantic.dataclasses import dataclass
from pydantic import ConfigDict


@dataclass(config=ConfigDict(validate_assignment=True))
class Form:
    href: str  # This should conform to anyURI
    op: Union[str, list[str]]
    contentType: str = "application/json"

@dataclass(config=ConfigDict(validate_assignment=True))
class DataSchema:
    title: Optional[str]
    description: Optional[str] = None
    const: Optional[Any] = None
    default: Optional[Any] = None
    unit: Optional[str] = None
    type: Optional[str] = None
    readonly: bool = False
    writeonly: bool = False

@dataclass(config=ConfigDict(validate_assignment=True))
class InteractionAffordance:
    title: Optional[str]
    forms: list[Form]
    description: Optional[str] = None

class PropertyAffordance(InteractionAffordance, DataSchema):
    observable: bool = False


@dataclass(config=ConfigDict(validate_assignment=True))
class ThingDescription:
    properties: list[PropertyAffordance]
