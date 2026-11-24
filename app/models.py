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
    delivery_address_line1: Mapped[Optional[str]] = mapped_column(String(150))
    delivery_address_line2: Mapped[Optional[str]] = mapped_column(String(150))
    delivery_postal_code: Mapped[Optional[str]] = mapped_column(String(20))
    delivery_city: Mapped[Optional[str]] = mapped_column(String(120))
    delivery_country: Mapped[Optional[str]] = mapped_column(String(120))
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    admin_notes: Mapped[Optional[str]] = mapped_column(Text)

    sessions = relationship('Session', back_populates='user', cascade='all, delete-orphan')
    customer_group_memberships = relationship('CustomerGroupMember', back_populates='user', cascade='all, delete-orphan')


class UserAccessInvite(Base):
    __tablename__ = 'user_access_invites'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


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


class Catalog(Base, TimestampMixin):
    __tablename__ = 'catalogs'

    slug: Mapped[str] = mapped_column(String(80), primary_key=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    icon: Mapped[Optional[str]] = mapped_column(String(80))
    minimum_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default='0.00')
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='1')

    categories = relationship('Category', back_populates='catalog')
    products = relationship('Product', back_populates='catalog')


class Category(Base, TimestampMixin):
    __tablename__ = 'categories'

    slug: Mapped[str] = mapped_column(String(80), primary_key=True)
    catalog_slug: Mapped[str] = mapped_column(ForeignKey('catalogs.slug'), nullable=False, default='villas', server_default='villas', index=True)
    parent_slug: Mapped[Optional[str]] = mapped_column(ForeignKey('categories.slug', ondelete='SET NULL'), index=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(80))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='1')
    visible_on_site: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='1')

    catalog = relationship('Catalog', back_populates='categories')
    parent = relationship('Category', remote_side=[slug], back_populates='children')
    children = relationship('Category', back_populates='parent')
    products = relationship('Product', back_populates='category')


class Product(Base, TimestampMixin):
    __tablename__ = 'products'

    ref: Mapped[str] = mapped_column(String(80), primary_key=True)
    catalog_slug: Mapped[str] = mapped_column(ForeignKey('catalogs.slug'), nullable=False, default='villas', server_default='villas', index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    product_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    category_slug: Mapped[Optional[str]] = mapped_column(ForeignKey('categories.slug'), index=True)
    brand: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    family: Mapped[Optional[str]] = mapped_column(String(120), index=True)
    ean: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    price_base: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3))
    eco_value: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False, default=Decimal('0.000'), server_default='0.000')
    pvp: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    case_inner: Mapped[Optional[int]] = mapped_column(Integer)
    case_outer: Mapped[Optional[int]] = mapped_column(Integer)
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
    gift_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default='0', index=True)

    catalog = relationship('Catalog', back_populates='products')
    category = relationship('Category', back_populates='products')
    cart_items = relationship('CartItem', back_populates='product')
    order_lines = relationship('OrderLine', back_populates='product')
    campaign_links = relationship('CampaignProduct', back_populates='product', cascade='all, delete-orphan')
    gift_promotion_links = relationship('GiftPromotionProduct', back_populates='product', cascade='all, delete-orphan', foreign_keys='GiftPromotionProduct.product_ref')


class Campaign(Base, TimestampMixin):
    __tablename__ = 'campaigns'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    show_text: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='1')
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default='0', index=True)
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    discount_type: Mapped[str] = mapped_column(String(20), nullable=False, default='none', server_default='none')
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False, default=Decimal('0.000'), server_default='0.000')
    image_path: Mapped[Optional[str]] = mapped_column(String(255))
    image_checksum: Mapped[Optional[str]] = mapped_column(String(64))
    image_mime_type: Mapped[Optional[str]] = mapped_column(String(100))

    products = relationship('CampaignProduct', back_populates='campaign', cascade='all, delete-orphan', order_by='CampaignProduct.sort_order')
    audiences = relationship('CampaignCustomerGroup', back_populates='campaign', cascade='all, delete-orphan')


class CampaignProduct(Base):
    __tablename__ = 'campaign_products'
    __table_args__ = (UniqueConstraint('campaign_id', 'product_ref', name='uq_campaign_products_campaign_product'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey('campaigns.id', ondelete='CASCADE'), nullable=False, index=True)
    product_ref: Mapped[str] = mapped_column(ForeignKey('products.ref', ondelete='CASCADE'), nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    promotional_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3))

    campaign = relationship('Campaign', back_populates='products')
    product = relationship('Product', back_populates='campaign_links')


class CustomerGroup(Base, TimestampMixin):
    __tablename__ = 'customer_groups'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='1')

    members = relationship('CustomerGroupMember', back_populates='group', cascade='all, delete-orphan')
    campaigns = relationship('CampaignCustomerGroup', back_populates='group', cascade='all, delete-orphan')


class CustomerGroupMember(Base):
    __tablename__ = 'customer_group_members'

    group_id: Mapped[int] = mapped_column(ForeignKey('customer_groups.id', ondelete='CASCADE'), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)

    group = relationship('CustomerGroup', back_populates='members')
    user = relationship('User', back_populates='customer_group_memberships')


class CampaignCustomerGroup(Base):
    __tablename__ = 'campaign_customer_groups'

    campaign_id: Mapped[int] = mapped_column(ForeignKey('campaigns.id', ondelete='CASCADE'), primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey('customer_groups.id', ondelete='CASCADE'), primary_key=True)

    campaign = relationship('Campaign', back_populates='audiences')
    group = relationship('CustomerGroup', back_populates='campaigns')


class GiftPromotion(Base, TimestampMixin):
    __tablename__ = 'gift_promotions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    catalog_slug: Mapped[str] = mapped_column(ForeignKey('catalogs.slug'), nullable=False, index=True)
    eligibility_mode: Mapped[str] = mapped_column(String(20), nullable=False, default='products', server_default='products')
    eligible_brands_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    condition_type: Mapped[str] = mapped_column(String(20), nullable=False, default='quantity', server_default='quantity')
    threshold_quantity: Mapped[Optional[int]] = mapped_column(Integer)
    threshold_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    gift_product_ref: Mapped[str] = mapped_column(ForeignKey('products.ref'), nullable=False, index=True)
    gift_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    max_redemptions_per_user: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default='0', index=True)
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)

    catalog = relationship('Catalog')
    gift_product = relationship('Product', foreign_keys=[gift_product_ref])
    products = relationship('GiftPromotionProduct', back_populates='promotion', cascade='all, delete-orphan')
    tiers = relationship('GiftPromotionTier', back_populates='promotion', cascade='all, delete-orphan', order_by='GiftPromotionTier.sort_order')
    redemptions = relationship('GiftPromotionRedemption', back_populates='promotion', cascade='all, delete-orphan')


class GiftPromotionProduct(Base):
    __tablename__ = 'gift_promotion_products'

    promotion_id: Mapped[int] = mapped_column(ForeignKey('gift_promotions.id', ondelete='CASCADE'), primary_key=True)
    product_ref: Mapped[str] = mapped_column(ForeignKey('products.ref', ondelete='CASCADE'), primary_key=True)

    promotion = relationship('GiftPromotion', back_populates='products')
    product = relationship('Product', back_populates='gift_promotion_links', foreign_keys=[product_ref])


class GiftPromotionTier(Base):
    __tablename__ = 'gift_promotion_tiers'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    promotion_id: Mapped[int] = mapped_column(ForeignKey('gift_promotions.id', ondelete='CASCADE'), nullable=False, index=True)
    minimum_threshold: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    maximum_threshold: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 3))
    gift_product_ref: Mapped[str] = mapped_column(ForeignKey('products.ref'), nullable=False, index=True)
    gift_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')

    promotion = relationship('GiftPromotion', back_populates='tiers')
    gift_product = relationship('Product', foreign_keys=[gift_product_ref])


class GiftPromotionRedemption(Base):
    __tablename__ = 'gift_promotion_redemptions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    promotion_id: Mapped[int] = mapped_column(ForeignKey('gift_promotions.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    promotion = relationship('GiftPromotion', back_populates='redemptions')
    user = relationship('User')
    order = relationship('Order')


class Cart(Base, TimestampMixin):
    __tablename__ = 'carts'

    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    catalog_revisions_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)
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
    unit_price_snapshot: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
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
    pdf_notes: Mapped[Optional[str]] = mapped_column(Text)
    include_pdf_notes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default='0')
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
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
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


class AdminAuditLog(Base):
    __tablename__ = 'admin_audit_logs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    actor_username: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(191), index=True)
    route: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    user_agent: Mapped[Optional[str]] = mapped_column(String(255))
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), index=True)


class ProductImportBatch(Base):
    __tablename__ = 'product_import_batches'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    actor_username: Mapped[str] = mapped_column(String(80), nullable=False)
    catalog_slug: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default='spreadsheet', server_default='spreadsheet')
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    changes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_categories_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default='applied', server_default='applied', index=True)
    rollback_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), index=True)
    rolled_back_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    rolled_back_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))


class DeveloperNote(Base, TimestampMixin):
    __tablename__ = 'developer_notes'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='1')
    created_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)


class UpdateAnnouncement(Base, TimestampMixin):
    __tablename__ = 'update_announcements'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default='stable', server_default='stable')
    selected_notes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='1', index=True)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)

    created_by_user = relationship('User', foreign_keys=[created_by_user_id])
    receipts = relationship('UpdateAnnouncementReceipt', back_populates='announcement', cascade='all, delete-orphan')


class UpdateAnnouncementReceipt(Base):
    __tablename__ = 'update_announcement_receipts'
    __table_args__ = (UniqueConstraint('announcement_id', 'user_id', name='uq_update_announcement_receipts_announcement_user'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    announcement_id: Mapped[int] = mapped_column(ForeignKey('update_announcements.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    viewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    ignored_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    announcement = relationship('UpdateAnnouncement', back_populates='receipts')
    user = relationship('User', foreign_keys=[user_id])


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
    pdf_notes: Mapped[Optional[str]] = mapped_column(Text)
    include_pdf_notes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default='0')
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
