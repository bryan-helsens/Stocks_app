"""Shared schema primitives and the disclaimer constant."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

#: Mandatory educational disclaimer attached to advisory-style responses (BR9).
DISCLAIMER_NL = (
    "Informatief en educatief — geen financieel, fiscaal of juridisch advies. "
    "Voorspellingen en scores zijn geen garanties."
)


class ORMModel(BaseModel):
    """Base for response models read from ORM objects."""

    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    """Generic message response."""

    message: str
