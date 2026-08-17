from __future__ import annotations

from datetime import datetime
from enum import Enum
from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, JSON, Boolean, DateTime, Enum as SAEnum, ForeignKey, Integer, MetaData, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship

naming_convention = {
    'ix': 'ix_%(column_0_label)s',
    'uq': 'uq_%(table_name)s_%(column_0_name)s',
    'ck': 'ck_%(table_name)s_%(constraint_name)s',
    'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
    'pk': 'pk_%(table_name)s',
}

Base = declarative_base(metadata=MetaData(naming_convention=naming_convention))


class UserRole(str, Enum):
    CLIENT = 'client'
    ADMIN = 'admin'
    DEVELOPER = 'developer'


class OrderStatus(str, Enum):
    PENDING = 'pending'
    CONFIRMED = 'confirmed'
    SHIPPED = 'shipped'


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class User(Base, TimestampMixin):
    __tablename__ = 'users'
    __table_args__ = (
        CheckConstraint("role in ('client', 'admin', 'developer')", name='ck_users_role_allowed'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(150), index=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    nif: Mapped[Optional[str]] = mapped_column(String(20))
    company_name: Mapped[Optional[str]] = mapped_column(String(150))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default=UserRole.CLIENT.value, server_default=UserRole.CLIENT.value, index=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='1')
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    phone: Mapped[Optional[str]] = mapped_column(String(30))
    address_line1: Mapped[Optional[str]] = mapped_column(String(150))
    address_line2: Mapped[Optional[str]] = mapped_column(String(150))
    postal_code: Mapped[Optional[str]] = mapped_column(String(20))
    city: Mapped[Optional[str]] = mapped_column(String(120))
    country: Mapped[Optional[str]] = mapped_column(String(120))
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    admin_notes: Mapped[Optional[str]] = mapped_column(Text)

    sessions = relationship('Session', back_populates='user', cascade='all, delete-orphan')


class Session(Base):
    __tablename__ = 'sessions'

    session_token_hash: Mapped[str] = mapped_column('session_id', String(128), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    user_agent: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    auth_context_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    user = relationship('User', back_populates='sessions')


class LoginRateLimit(Base):
    __tablename__ = 'login_rate_limits'

    bucket_key: Mapped[str] = mapped_column(String(191), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    blocked_until: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class Category(Base, TimestampMixin):
    __tablename__ = 'categories'

    slug: Mapped[str] = mapped_column(String(80), primary_key=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='1')
    visible_on_site: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='1')

    products = relationship('Product', back_populates='category')


class Product(Base, TimestampMixin):
    __tablename__ = 'products'

    ref: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    product_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    category_slug: Mapped[Optional[str]] = mapped_column(ForeignKey('categories.slug'), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    pvp: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    colors_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    sizes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    image_path: Mapped[Optional[str]] = mapped_column(String(255))
    image_checksum: Mapped[Optional[str]] = mapped_column(String(64))
    image_mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='1')
    manual_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='1')
    season: Mapped[str] = mapped_column(String(20), nullable=False, default='ambos', server_default='ambos')
    quantity_step: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    description: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    category = relationship('Category', back_populates='products')
    cart_items = relationship('CartItem', back_populates='product')
    order_lines = relationship('OrderLine', back_populates='product')


class Cart(Base, TimestampMixin):
    __tablename__ = 'carts'

    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    source_version: Mapped[Optional[str]] = mapped_column(String(32))
    user = relationship('User', foreign_keys=[user_id])
    items = relationship('CartItem', back_populates='cart', cascade='all, delete-orphan')


class CartItem(Base, TimestampMixin):
    __tablename__ = 'cart_items'
    __table_args__ = (UniqueConstraint('cart_user_id', 'product_ref', 'color', 'size', name='uq_cart_item_variant'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cart_user_id: Mapped[int] = mapped_column(ForeignKey('carts.user_id', ondelete='CASCADE'), nullable=False, index=True)
    product_ref: Mapped[str] = mapped_column(ForeignKey('products.ref'), nullable=False, index=True)
    color: Mapped[str] = mapped_column(String(80), nullable=False, default='')
    size: Mapped[str] = mapped_column(String(80), nullable=False, default='')
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price_snapshot: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    line_total_snapshot: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    product_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    product_type_snapshot: Mapped[str] = mapped_column(String(80), nullable=False)
    product_image_snapshot: Mapped[Optional[str]] = mapped_column(String(255))
    product_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    cart = relationship('Cart', back_populates='items')
    product = relationship('Product', back_populates='cart_items')


class CartOperation(Base, TimestampMixin):
    __tablename__ = 'cart_operations'
    __table_args__ = (UniqueConstraint('user_id', 'idempotency_key', name='uq_cart_operations_user_key'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    cart_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    response_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class Order(Base, TimestampMixin):
    __tablename__ = 'orders'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id'), index=True)
    origin: Mapped[str] = mapped_column(String(32), nullable=False, default='client', server_default='client')
    customer_name: Mapped[str] = mapped_column(String(150), nullable=False)
    customer_nif: Mapped[Optional[str]] = mapped_column(String(20))
    customer_email: Mapped[Optional[str]] = mapped_column(String(150))
    customer_phone: Mapped[Optional[str]] = mapped_column(String(30))
    customer_company: Mapped[Optional[str]] = mapped_column(String(150))
    customer_address_line1: Mapped[Optional[str]] = mapped_column(String(150))
    customer_address_line2: Mapped[Optional[str]] = mapped_column(String(150))
    customer_postal_code: Mapped[Optional[str]] = mapped_column(String(20))
    customer_city: Mapped[Optional[str]] = mapped_column(String(120))
    customer_country: Mapped[Optional[str]] = mapped_column(String(120))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    lines: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    order_status: Mapped[str] = mapped_column(String(32), nullable=False, default='pending', server_default='pending')
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    email_status: Mapped[str] = mapped_column(String(32), nullable=False, default='pending', server_default='pending')
    email_error: Mapped[Optional[str]] = mapped_column(Text)
    email_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    customer_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    user = relationship('User', foreign_keys=[user_id])
    created_by_user = relationship('User', foreign_keys=[created_by_user_id])
    items = relationship('OrderLine', back_populates='order', cascade='all, delete-orphan')
    history = relationship('OrderStatusHistory', back_populates='order', cascade='all, delete-orphan')


class OrderLine(Base):
    __tablename__ = 'order_lines'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)
    product_ref: Mapped[str] = mapped_column(ForeignKey('products.ref'), nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_type: Mapped[str] = mapped_column(String(80), nullable=False)
    color: Mapped[str] = mapped_column(String(80), nullable=False, default='')
    size: Mapped[str] = mapped_column(String(80), nullable=False, default='')
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    order = relationship('Order', back_populates='items')
    product = relationship('Product', back_populates='order_lines')


class OrderStatusHistory(Base):
    __tablename__ = 'order_status_history'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)
    old_status: Mapped[Optional[str]] = mapped_column(String(32))
    new_status: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id'))
    request_id: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    note: Mapped[Optional[str]] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    order = relationship('Order', back_populates='history')


class OrderRequestId(Base):
    __tablename__ = 'order_request_ids'

    request_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, unique=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class SiteSetting(Base):
    __tablename__ = 'site_settings'

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class EmailTemplate(Base, TimestampMixin):
    __tablename__ = 'email_templates'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    body_text: Mapped[Optional[str]] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='1')


class EmailDeliveryLog(Base, TimestampMixin):
    __tablename__ = 'email_delivery_logs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    related_order_id: Mapped[Optional[int]] = mapped_column(ForeignKey('orders.id', ondelete='SET NULL'), index=True)
    related_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    template_name: Mapped[Optional[str]] = mapped_column(String(120))
    request_id: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    recipient: Mapped[str] = mapped_column(String(150), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(255))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class LoginLog(Base):
    __tablename__ = 'login_logs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    username_input: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default='0')
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    user_agent: Mapped[Optional[str]] = mapped_column(String(255))
    failure_reason: Mapped[Optional[str]] = mapped_column(String(80))
    request_id: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class ErrorLog(Base):
    __tablename__ = 'error_logs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    scope: Mapped[str] = mapped_column(String(120), nullable=False)
    message: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text)
    level: Mapped[str] = mapped_column(String(16), nullable=False, default='error', server_default='error')
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class DeveloperNote(Base, TimestampMixin):
    __tablename__ = 'developer_notes'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='1')
    created_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)


class AdminWarningIgnore(Base):
    __tablename__ = 'admin_warning_ignores'
    __table_args__ = (
        UniqueConstraint('warning_key', name='uq_admin_warning_ignores_warning_key'),
        UniqueConstraint('warning_type', 'entity_type', 'entity_id', 'warning_key', name='uq_admin_warning_ignores_identity'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    warning_key: Mapped[str] = mapped_column(String(191), nullable=False, index=True)
    warning_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    ignored_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    ignored_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    reason: Mapped[Optional[str]] = mapped_column(Text)


class AdminOrderDraft(Base, TimestampMixin):
    __tablename__ = 'admin_order_drafts'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    customer_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    request_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='1')
    notes: Mapped[Optional[str]] = mapped_column(Text)
    draft_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    admin_user = relationship('User', foreign_keys=[admin_user_id])
    customer_user = relationship('User', foreign_keys=[customer_user_id])
    lines = relationship('AdminOrderDraftLine', back_populates='draft', cascade='all, delete-orphan')


class AdminOrderDraftLine(Base, TimestampMixin):
    __tablename__ = 'admin_order_draft_lines'
    __table_args__ = (
        UniqueConstraint('draft_id', 'product_ref', 'color', 'size', name='uq_admin_order_draft_lines_variant'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey('admin_order_drafts.id', ondelete='CASCADE'), nullable=False, index=True)
    product_ref: Mapped[str] = mapped_column(ForeignKey('products.ref'), nullable=False, index=True)
    color: Mapped[str] = mapped_column(String(80), nullable=False, default='')
    size: Mapped[str] = mapped_column(String(80), nullable=False, default='')
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    line_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    draft = relationship('AdminOrderDraft', back_populates='lines')
