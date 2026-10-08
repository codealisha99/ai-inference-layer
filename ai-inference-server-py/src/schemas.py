"""Pydantic models that describe the HTTP contract.

Handlers validate requests by hand (so error messages stay identical across all four language
ports), so these models are used for the OpenAPI document, and the tests validate real
responses against them. That keeps the published docs honest.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ModelType = Literal["text-generation", "text-classification", "embedding"]


# ---- requests ------------------------------------------------------------------------


class ModelCreate(BaseModel):
    name: str = Field(
        description="Unique model name. Leading and trailing whitespace is trimmed.",
        examples=["sentiment"],
    )
    type: ModelType = Field(description="Which engine runs this model.")
    config: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional engine settings. `embedding`: `dimensions` (integer 1-1024, default 5). "
            "`text-generation`: `maxChars` (positive integer) truncates the output. "
            "Unknown keys are stored and ignored."
        ),
        examples=[{"dimensions": 64}],
    )


class InferRequest(BaseModel):
    input: str = Field(
        min_length=1, description="Text to run through the model.", examples=["not bad at all"]
    )


class BatchRequest(BaseModel):
    inputs: list[str] = Field(
        min_length=1,
        description=(
            "Texts to run, in order. At most `MAX_BATCH_SIZE` (default 64) non-empty strings. "
            "The batch is atomic: if any item is invalid, nothing is run or stored."
        ),
        examples=[["great", "terrible", "a wooden table"]],
    )


# ---- resources -----------------------------------------------------------------------


class Model(BaseModel):
    id: str = Field(examples=["3f2a9c1e5b7d4e8f9a0b1c2d3e4f5a6b"])
    name: str = Field(examples=["sentiment"])
    type: ModelType
    config: dict[str, Any]
    createdAt: int = Field(description="Unix time in milliseconds.", examples=[1791489234129])


class TextOutput(BaseModel):
    text: str = Field(examples=["Generated response for: hello"])


class ClassificationOutput(BaseModel):
    label: Literal["positive", "negative", "neutral"]
    score: float = Field(ge=0, le=1, description="Confidence in `label`.", examples=[0.7311])


class EmbeddingOutput(BaseModel):
    embedding: list[float] = Field(description="Unit-length vector.")


class Inference(BaseModel):
    id: str
    modelId: str
    input: str
    status: Literal["pending", "running", "completed", "failed"]
    output: TextOutput | ClassificationOutput | EmbeddingOutput | None
    createdAt: int = Field(description="Unix time in milliseconds.")
    completedAt: int | None = Field(description="Unix time in milliseconds.")
    latencyMs: float = Field(description="Time spent in the engine.", examples=[0.012])


class Deleted(BaseModel):
    id: str
    removed: Literal[True]


class Health(BaseModel):
    status: Literal["ok"]
    version: str
    storage: Literal["memory", "sqlite"]
    uptimeSeconds: float
    models: int
    inferences: int


class Probe(BaseModel):
    status: Literal["alive", "ready"]
    storage: Literal["memory", "sqlite"] | None = None


# ---- the {success, data, error} envelope ---------------------------------------------


class _Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    success: bool
    error: str | None


class ErrorResponse(_Envelope):
    success: Literal[False]
    data: None
    error: str = Field(examples=["model not found"])


class ModelResponse(_Envelope):
    success: Literal[True]
    data: Model
    error: None


class ModelListResponse(_Envelope):
    success: Literal[True]
    data: list[Model]
    error: None


class InferenceResponse(_Envelope):
    success: Literal[True]
    data: Inference
    error: None


class InferenceListResponse(_Envelope):
    success: Literal[True]
    data: list[Inference]
    error: None


class DeletedResponse(_Envelope):
    success: Literal[True]
    data: Deleted
    error: None


class HealthResponse(_Envelope):
    success: Literal[True]
    data: Health
    error: None


class ProbeResponse(_Envelope):
    success: Literal[True]
    data: Probe
    error: None


SCHEMAS: tuple[type[BaseModel], ...] = (
    ModelCreate,
    InferRequest,
    BatchRequest,
    ErrorResponse,
    ModelResponse,
    ModelListResponse,
    InferenceResponse,
    InferenceListResponse,
    DeletedResponse,
    HealthResponse,
    ProbeResponse,
)
