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
    catalog_slug: str = 'villas'
    items: list[CartItemInput] = Field(default_factory=list)
    csrf_token: str | None = None


class CartMutationInput(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=80)
    cart_revision: int | None = None
    catalog_slug: str = 'villas'
    ref: str
    color: str | None = None
    size: str | None = None
    quantity: int | None = None
    csrf_token: str | None = None


class CartItemUpdateInput(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=80)
    cart_revision: int | None = None
    catalog_slug: str = 'villas'
    quantity: int
    ignore_quantity_step: bool = False
    csrf_token: str | None = None


class CartDeleteInput(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=80)
    cart_revision: int | None = None
    catalog_slug: str = 'villas'
    csrf_token: str | None = None


class OrderSubmitInput(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=80)
    cart_revision: int | None = None
    catalog_slug: str = 'villas'
    notes: str | None = None
    pdf_notes: str | None = None
    include_pdf_notes: bool = False
    customer_user_id: int | None = None
    ignore_quantity_step: bool = False
    ignore_minimum_total: bool = False
    csrf_token: str | None = None
