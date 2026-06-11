import math
import re
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field

CADASTRAL_NUMBER_PATTERN = re.compile(r"^\d+:\d+:\d+:\d+$")
CADASTRAL_NUMBER_ERROR = (
    "Cadastral number must contain four numeric parts separated by colons, "
    "for example 77:01:0004012:2054."
)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EMAIL_ERROR = "Email must be a valid email address."


def validate_cadastral_number(value: str) -> str:
    normalized_value = value.strip()

    if len(normalized_value) > 255 or not CADASTRAL_NUMBER_PATTERN.fullmatch(
        normalized_value
    ):
        raise ValueError(CADASTRAL_NUMBER_ERROR)

    return normalized_value


def validate_optional_cadastral_number(value: str | None) -> str | None:
    if value is None:
        return None

    return validate_cadastral_number(value)


def validate_email(value: str) -> str:
    normalized_value = value.strip().lower()

    if len(normalized_value) > 255 or not EMAIL_PATTERN.fullmatch(normalized_value):
        raise ValueError(EMAIL_ERROR)

    return normalized_value


def validate_json_number(value: object) -> object:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Coordinate must be a JSON number.")

    return value


def validate_latitude(value: float) -> float:
    if not math.isfinite(value) or not -90 <= value <= 90:
        raise ValueError("Latitude must be a finite number between -90 and 90.")

    return value


def validate_longitude(value: float) -> float:
    if not math.isfinite(value) or not -180 <= value <= 180:
        raise ValueError("Longitude must be a finite number between -180 and 180.")

    return value


CadastralNumber = Annotated[
    str,
    Field(
        description="Cadastral number in four-part colon-separated format.",
        examples=["77:01:0004012:2054"],
    ),
    AfterValidator(validate_cadastral_number),
]
OptionalCadastralNumber = Annotated[
    str | None,
    Field(
        description="Optional cadastral number filter.",
        examples=["77:01:0004012:2054"],
    ),
    AfterValidator(validate_optional_cadastral_number),
]
Email = Annotated[
    str,
    Field(
        description="User email address.",
        examples=["user@example.com"],
        max_length=255,
    ),
    AfterValidator(validate_email),
]
Password = Annotated[
    str,
    Field(
        description="User password.",
        min_length=8,
        max_length=128,
    ),
]
Latitude = Annotated[
    float,
    Field(description="Latitude in degrees from -90 to 90."),
    BeforeValidator(validate_json_number),
    AfterValidator(validate_latitude),
]
Longitude = Annotated[
    float,
    Field(description="Longitude in degrees from -180 to 180."),
    BeforeValidator(validate_json_number),
    AfterValidator(validate_longitude),
]


class QueryRequest(BaseModel):
    cadastral_number: CadastralNumber
    latitude: Latitude
    longitude: Longitude


class QueryResponse(BaseModel):
    result: bool


class RegisterRequest(BaseModel):
    email: Email
    password: Password


class LoginRequest(BaseModel):
    email: Email
    password: Password


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserPublic(BaseModel):
    id: int
    email: str
    is_active: bool
    is_admin: bool
    created_at: datetime


class UserInDB(UserPublic):
    hashed_password: str


class HistoryItem(BaseModel):
    id: int
    cadastral_number: str
    latitude: float
    longitude: float
    result: bool
    created_at: datetime


class AdminHistoryItem(HistoryItem):
    user_id: int | None
