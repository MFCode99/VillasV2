from __future__ import annotations

from pydantic import BaseModel, Field


class CartItemInput(BaseModel):
    ref: str
    color: str | None = None
    size: str | None = None
    quantity: int | None = None


class CartReplaceInput(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=80)
    cart_revision: int | None = None
    items: list[CartItemInput] = Field(default_factory=list)
    csrf_token: str | None = None


class CartMutationInput(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=80)
    cart_revision: int | None = None
    ref: str
    color: str | None = None
    size: str | None = None
    quantity: int | None = None
    csrf_token: str | None = None


class CartItemUpdateInput(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=80)
    cart_revision: int | None = None
    quantity: int
    csrf_token: str | None = None


class CartDeleteInput(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=80)
    cart_revision: int | None = None
    csrf_token: str | None = None


class OrderSubmitInput(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=80)
    cart_revision: int | None = None
    notes: str | None = None
    customer_user_id: int | None = None
    csrf_token: str | None = None
