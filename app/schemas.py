import math
import re
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

CADASTRAL_NUMBER_PATTERN = re.compile(r"^\d+:\d+:\d+:\d+$")
CADASTRAL_NUMBER_ERROR = (
    "Cadastral number must contain four numeric parts separated by colons, "
    "for example 77:01:0004012:2054."
)


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
Latitude = Annotated[
    float,
    Field(description="Latitude in degrees from -90 to 90."),
    AfterValidator(validate_latitude),
]
Longitude = Annotated[
    float,
    Field(description="Longitude in degrees from -180 to 180."),
    AfterValidator(validate_longitude),
]


class QueryRequest(BaseModel):
    cadastral_number: CadastralNumber
    latitude: Latitude
    longitude: Longitude


class QueryResponse(BaseModel):
    result: bool


class HistoryItem(BaseModel):
    id: int
    cadastral_number: str
    latitude: float
    longitude: float
    result: bool
    created_at: datetime
