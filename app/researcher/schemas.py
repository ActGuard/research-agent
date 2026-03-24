"""Pydantic schemas for structured LLM outputs."""

from typing import Literal

from pydantic import BaseModel


class TextResponse(BaseModel):
    text: str


class QueryClassification(BaseModel):
    query_type: Literal["quick", "standard", "deep", "comparison"] = "standard"
