"""Pydantic models for request/response."""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


class SessionState(BaseModel):
    session_id: str
    step: int = 0
    venue_type: Optional[str] = None
    num_inputs: Optional[int] = None
    num_outputs: Optional[int] = None
    resolution: Optional[str] = None
    hdr_required: Optional[bool] = None
    max_distance_m: Optional[int] = None
    signal_type: Optional[str] = None
    budget_usd: Optional[int] = None
    notes: Optional[str] = None
    category_hint: Optional[str] = None
    # Scenario planner state (stored as JSON strings to stay DB-compatible)
    _scenario_plan: Optional[str] = None
    _scenario_answers: Optional[str] = None
    _clarification_round: Optional[int] = None


class SessionUpdate(BaseModel):
    venue_type: Optional[str] = None
    num_inputs: Optional[int] = None
    num_outputs: Optional[int] = None
    resolution: Optional[str] = None
    hdr_required: Optional[bool] = None
    max_distance_m: Optional[int] = None
    signal_type: Optional[str] = None
    budget_usd: Optional[int] = None
    notes: Optional[str] = None
    category_hint: Optional[str] = None
    _scenario_plan: Optional[str] = None
    _scenario_answers: Optional[str] = None
    _clarification_round: Optional[int] = None


class Product(BaseModel):
    id: str
    name: str
    category: str
    inputs: Optional[int]
    outputs: Optional[int]
    input_signals: list[str] = []
    output_signals: list[str] = []
    resolutions: list[str] = []
    max_bandwidth_gbps: Optional[float]
    max_distance_m: Optional[int]
    price_usd: Optional[float] = None
    stock_status: Optional[str] = None
    product_url: Optional[str] = None
    image_url: Optional[str] = None
    manual_file: Optional[str]
    notes: Optional[str]


class ManualChunk(BaseModel):
    product_id: str
    heading: str
    text: str
    doc_type: str
    has_limitation: bool
    summary: str
    relevance: float


class RecommendRequest(BaseModel):
    session_id: str
    question: Optional[str] = None   # extra free-text question from customer


class RecommendResponse(BaseModel):
    answer: str
    candidates: list[Product]
    chunks_used: list[ManualChunk]
    session: SessionState
