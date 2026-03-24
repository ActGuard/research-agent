"""Pydantic schemas for structured LLM outputs."""

from pydantic import BaseModel


class TextResponse(BaseModel):
    text: str
