from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from .models import Campaign, CampaignCustomerGroup, CampaignProduct, CustomerGroupMember, Product, User
from .security import utcnow


UNIT_PRICE = Decimal('0.001')


@dataclass(frozen=True, slots=True)
class PromotionInfo:
    campaign_id: int
    campaign_title: str
    original_price: Decimal
    price: Decimal
    discount_type: str
    discount_value: Decimal

    @property
    def label(self) -> str:
        if self.discount_type == 'percentage':
            return f'-{self.discount_value.normalize()}%'
        return f'-{(self.original_price - self.price):.2f} €'


def price_for_campaign(product: Product, campaign: Campaign, link: CampaignProduct) -> Decimal:
    original = Decimal(str(product.price or 0))
    if link.promotional_price is not None:
        result = Decimal(str(link.promotional_price))
    elif campaign.discount_type == 'percentage':
        result = original * (Decimal('1') - Decimal(str(campaign.discount_value or 0)) / Decimal('100'))
    elif campaign.discount_type == 'fixed_amount':
        result = original - Decimal(str(campaign.discount_value or 0))
    else:
        result = original
    return max(Decimal('0'), result).quantize(UNIT_PRICE, rounding=ROUND_HALF_UP)


def active_promotions(db: Session, user_id: int, products: Iterable[Product]) -> dict[str, PromotionInfo]:
    product_map = {product.ref: product for product in products}
    if not product_map:
        return {}
    now = utcnow()
    links = list(db.scalars(
        select(CampaignProduct)
        .join(Campaign, Campaign.id == CampaignProduct.campaign_id)
        .options(selectinload(CampaignProduct.campaign).selectinload(Campaign.audiences).selectinload(CampaignCustomerGroup.group))
        .where(
            CampaignProduct.product_ref.in_(product_map),
            Campaign.active.is_(True),
            or_(Campaign.starts_at.is_(None), Campaign.starts_at <= now),
            or_(Campaign.ends_at.is_(None), Campaign.ends_at >= now),
        )
    ).unique().all())
    user = db.get(User, user_id)
    all_audiences = bool(user and user.role in {'admin', 'developer'})
    user_group_ids = set(db.scalars(select(CustomerGroupMember.group_id).where(CustomerGroupMember.user_id == user_id)).all()) if not all_audiences else set()
    result: dict[str, PromotionInfo] = {}
    for link in links:
        campaign = link.campaign
        if campaign.audiences and not all_audiences and not any(audience.group_id in user_group_ids and audience.group and audience.group.active for audience in campaign.audiences):
            continue
        product = product_map[link.product_ref]
        original = Decimal(str(product.price or 0)).quantize(UNIT_PRICE, rounding=ROUND_HALF_UP)
        price = price_for_campaign(product, campaign, link)
        if price >= original:
            continue
        promotion = PromotionInfo(campaign.id, campaign.title, original, price, campaign.discount_type if link.promotional_price is None else 'promotional_price', Decimal(str(campaign.discount_value or 0)))
        if link.product_ref not in result or price < result[link.product_ref].price:
            result[link.product_ref] = promotion
    return result
