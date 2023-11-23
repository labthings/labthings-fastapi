# This file was generated by `datamodel-code-generator`, using
# the command
# datamodel-codegen  --input person.json --input-file-type jsonschema --output model.py
# I then manually simplified it a bit, mostly by deduplicating/using inheritance.
# It's now been fairly extensively changed, to update to pydantic 2 and use generic
# models.

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import (
    Any,
    Annotated,
    Dict,
    List,
    Optional,
    Union,
    TypeVar,
    Generic,
    Mapping,
    Literal,
)
from pydantic import AnyUrl, BaseModel, Field, ConfigDict, AfterValidator


class Version(BaseModel):
    instance: str


AnyUri = str
Description = str
Descriptions = Optional[Dict[str, str]]
Title = str
Titles = Optional[Dict[str, str]]
Security = Union[List[str], str]
Scopes = Union[List[str], str]
TypeDeclaration = Union[str, List[str]]

# From the spec, TypeDeclaration should be in:
# boolean, integer, number, string, object,
# array, or null


class Subprotocol(Enum):
    longpoll = "longpoll"
    websub = "websub"
    sse = "sse"


THING_CONTEXT_URL = "https://www.w3.org/2022/wot/td/v1.1"
THING_CONTEXT_URL_v1 = "https://www.w3.org/2019/wot/td/v1"


ThingContextType = Union[
    List[Union[AnyUri, Dict]],
    AnyUri,
]


def uses_thing_context(v: ThingContextType):
    if not isinstance(v, list):
        assert v is THING_CONTEXT_URL
    else:
        assert (
            v[0] == THING_CONTEXT_URL
            or v[1] == THING_CONTEXT_URL
            and v[0] == THING_CONTEXT_URL_v1
        )


ThingContext = Annotated[
    ThingContextType,
    AfterValidator(uses_thing_context),
]


class Type(Enum):
    boolean = "boolean"
    integer = "integer"
    number = "number"
    string = "string"
    object = "object"
    array = "array"
    null = "null"


class DataSchema(BaseModel):
    field_type: Optional[TypeDeclaration] = Field(None, alias="@type")
    description: Optional[Description] = None
    title: Optional[Title] = None
    descriptions: Optional[Descriptions] = None
    titles: Optional[Titles] = None
    writeOnly: Optional[bool] = None
    readOnly: Optional[bool] = None
    oneOf: Optional[list[DataSchema]] = None
    unit: Optional[str] = None
    enum: Optional[list] = None
    # enum was `Field(None, min_length=1, unique_items=True)` but this failed with
    # generic models
    format: Optional[str] = None
    const: Optional[Any] = None
    default: Optional[Any] = None
    type: Optional[Type] = None
    # The fields below should be empty unless type==Type.array
    items: Optional[Union[DataSchema, List[DataSchema]]] = None
    maxItems: Optional[int] = Field(None, ge=0)
    minItems: Optional[int] = Field(None, ge=0)
    # The fields below should be empty unless type==Type.number or Type.integer
    minimum: Optional[Union[int, float]] = None
    maximum: Optional[Union[int, float]] = None
    exclusiveMinimum: Optional[Union[int, float]] = None
    exclusiveMaximum: Optional[Union[int, float]] = None
    multipleOf: Optional[Union[int, float]] = None
    # The fields below should be empty unless type==Type.object
    properties: Optional[Mapping[str, DataSchema]] = None
    required: Optional[list[str]] = None
    # The fields below should be empty unless type==Type.string
    minLength: Optional[int] = None
    maxLength: Optional[int] = None
    pattern: Optional[str] = None
    contentEncoding: Optional[str] = None
    contentMediaType: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


"""
# The classes below attempted to implement the w3c spec for type-specific fields.
# However, this is very hard without complicated logic - and the w3c JSONSchema
# simply defines one DataSchema type, as I have done above.
# The code below almost but not quite works.

class ArraySchema(DataSchema):
    type: Type = Literal[Type.array]
    items: Optional[Union[DataSchema, List[DataSchema]]] = None
    maxItems: Optional[conint(ge=0)] = None
    minItems: Optional[conint(ge=0)] = None


numberT = TypeVar("numberT", int, float)
class GenericNumberSchema(DataSchema, BaseModel, Generic[numberT]):
    minimum: Optional[numberT] = None
    maximum: Optional[numberT] = None
    exclusiveMinimum: Optional[numberT] = None
    exclusiveMaximum: Optional[numberT] = None
    multipleOf: Optional[numberT] = None


class NumberSchema(GenericNumberSchema[float]):
    type: Type = Literal[Type.number]


class IntegerSchema(GenericNumberSchema[int]):
    type: Type = Literal[Type.integer]
    

class BooleanSchema(DataSchema):
    type: Type = Literal[Type.boolean]


class ObjectSchema(DataSchema):
    type: Type = Literal[Type.object]
    properties: Optional[Mapping[str, DataSchema]] = None
    required: Optional[List[str]] = None


class StringSchema(DataSchema):
    type: Type = Literal[Type.string]
    minLength: Optional[int] = None
    maxLength: Optional[int] = None
    pattern: Optional[str] = None
    contentEncoding: Optional[str] = None
    contentMediaType: Optional[str] = None


class NullSchema(DataSchema):
    type: Type = Literal[Type.object]


DataSchema: Type = Union[
    DataSchema, 
    ArraySchema,
    BooleanSchema,
    IntegerSchema,
    NullSchema,
    NumberSchema,
    ObjectSchema,
    StringSchema,
]


DATA_SCHEMA_MODELS: list[BaseModel] = [
    DataSchema, 
    ArraySchema,
    BooleanSchema,
    IntegerSchema,
    NullSchema,
    NumberSchema,
    ObjectSchema,
    StringSchema,
]
for model in DATA_SCHEMA_MODELS:
    model.update_forward_refs()
"""


class Response(BaseModel):
    contentType: Optional[str] = None


class PropertyOp(Enum):
    readproperty = "readproperty"
    writeproperty = "writeproperty"
    observeproperty = "observeproperty"
    unobserveproperty = "unobserveproperty"


class ActionOp(Enum):
    invokeaction = "invokeaction"


class EventOp(Enum):
    subscribeevent = "subscribeevent"
    unsubscribeevent = "unsubscribeevent"


class RootOp(Enum):
    readallproperties = "readallproperties"
    writeallproperties = "writeallproperties"
    readmultipleproperties = "readmultipleproperties"
    writemultipleproperties = "writemultipleproperties"


Op = Union[PropertyOp, ActionOp, EventOp, RootOp]


OpT = TypeVar("OpT")


class Form(BaseModel, Generic[OpT]):
    model_config = ConfigDict(extra="allow")

    href: AnyUri
    op: Optional[Union[OpT, List[OpT]]] = None
    contentType: Optional[str] = None
    contentCoding: Optional[str] = None
    subprotocol: Optional[Subprotocol] = None
    security: Optional[Security] = None
    scopes: Optional[Scopes] = None
    response: Optional[Response] = None


class InteractionAffordance(BaseModel):
    model_config = ConfigDict(extra="allow")

    description: Optional[Description] = None
    descriptions: Optional[Descriptions] = None
    title: Optional[Title] = None
    titles: Optional[Titles] = None
    forms: List[Form] = Field(..., min_length=1)
    uriVariables: Optional[Dict[str, DataSchema]] = None


class PropertyAffordance(InteractionAffordance, DataSchema):
    observable: Optional[bool] = None
    forms: List[Form[PropertyOp]] = Field(..., min_length=1)


class ActionAffordance(InteractionAffordance):
    field_type: Optional[TypeDeclaration] = Field(None, alias="@type")
    input: Optional[DataSchema] = None
    output: Optional[DataSchema] = None
    safe: Optional[bool] = None
    idempotent: Optional[bool] = None
    forms: List[Form[ActionOp]] = Field(..., min_length=1)


class EventAffordance(BaseModel):
    field_type: Optional[TypeDeclaration] = Field(None, alias="@type")
    subscription: Optional[DataSchema] = None
    data: Optional[DataSchema] = None
    cancellation: Optional[DataSchema] = None
    forms: List[Form[EventOp]] = Field(..., min_length=1)


class LinkElement(BaseModel):
    model_config = ConfigDict(extra="allow")

    href: AnyUri
    type: Optional[str] = None
    rel: Optional[str] = None
    anchor: Optional[AnyUri] = None


Links = Optional[List[LinkElement]]


class SecuritySchemeEnum(Enum):
    nosec = "nosec"  # was Scheme
    basic = "basic"  # was Scheme1
    digest = "digest"  # was Scheme2
    apikey = "apikey"  # was Scheme3
    bearer = "bearer"  # was Scheme4
    psk = "psk"  # was Scheme5
    oauth2 = "oauth2"  # was Scheme6


class In(Enum):
    header = "header"
    query = "query"
    body = "body"
    cookie = "cookie"


class Qop(Enum):
    auth = "auth"
    auth_int = "auth-int"


class Flow(Enum):
    code = "code"


class BaseSecurityScheme(BaseModel):
    field_type: Optional[TypeDeclaration] = Field(None, alias="@type")
    description: Optional[Description] = None
    descriptions: Optional[Descriptions] = None
    proxy: Optional[AnyUri] = None
    scheme: SecuritySchemeEnum


class NoSecurityScheme(BaseSecurityScheme):
    scheme: Literal[SecuritySchemeEnum.nosec] = SecuritySchemeEnum.nosec
    description: Optional[Description] = Field(
        default_factory=lambda: Description("No security")
    )


class NameAndIn(BaseModel):
    in_: Optional[In] = Field(None, alias="in")  # for scheme=basic,digest,apikey,bearer
    name: Optional[str] = None  # for scheme=basic,digest,apikey,bearer


class BasicSecurityScheme(BaseSecurityScheme, NameAndIn):
    scheme: Literal[SecuritySchemeEnum.basic] = SecuritySchemeEnum.basic


class DigestSecurityScheme(BaseSecurityScheme, NameAndIn):
    scheme: Literal[SecuritySchemeEnum.digest] = SecuritySchemeEnum.digest
    qop: Optional[Qop] = None  # for scheme=digest


class APISecurityScheme(BaseSecurityScheme, NameAndIn):
    scheme: Literal[SecuritySchemeEnum.apikey] = SecuritySchemeEnum.apikey


class BearerSecurityScheme(BaseSecurityScheme, NameAndIn):
    scheme: Literal[SecuritySchemeEnum.bearer] = SecuritySchemeEnum.bearer
    authorization: Optional[AnyUri] = None  # for scheme=bearer,oauth2
    alg: Optional[str] = None  # for scheme=bearer
    format: Optional[str] = None  # for scheme=bearer


class PskSecurityScheme(BaseSecurityScheme):
    scheme: Literal[SecuritySchemeEnum.psk] = SecuritySchemeEnum.psk
    identity: Optional[str] = None  # for scheme=psk


class Oauth2SecurityScheme(BaseSecurityScheme):
    scheme: Literal[SecuritySchemeEnum.oauth2] = SecuritySchemeEnum.oauth2
    authorization: Optional[AnyUri] = None  # for scheme=bearer,oauth2
    token: Optional[AnyUri] = None  # for schema=oauth2
    refresh: Optional[AnyUri] = None  # for scheme=oauth2
    scopes: Optional[Union[List[str], str]] = None  # oauth2
    flow: Optional[Flow] = None  # for scheme=oauth2


SecurityScheme = Union[
    BaseSecurityScheme,
    NoSecurityScheme,
    BasicSecurityScheme,
    DigestSecurityScheme,
    APISecurityScheme,
    BearerSecurityScheme,
    PskSecurityScheme,
    Oauth2SecurityScheme,
]


class WotTdSchema16October2019(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: Optional[AnyUrl] = None
    title: Title
    titles: Optional[Titles] = None
    properties: Optional[Dict[str, PropertyAffordance]] = None
    actions: Optional[Dict[str, ActionAffordance]] = None
    events: Optional[Dict[str, EventAffordance]] = None
    description: Optional[Description] = None
    descriptions: Optional[Descriptions] = None
    version: Optional[Version] = None
    links: Links = None
    forms: Optional[List[Form[RootOp]]] = Field(None, min_length=1)
    base: Optional[AnyUri] = None
    securityDefinitions: Dict[str, SecurityScheme]
    support: Optional[AnyUri] = None
    created: Optional[datetime] = None
    modified: Optional[datetime] = None
    security: Union[str, List[str]]
    field_type: Optional[TypeDeclaration] = Field(None, alias="@type")
    field_context: ThingContext = Field(
        THING_CONTEXT_URL,
        alias="@context",
    )


ThingDescription = WotTdSchema16October2019
