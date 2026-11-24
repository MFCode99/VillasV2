from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Iterable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from .models import GiftPromotion, GiftPromotionProduct, GiftPromotionRedemption, Product


@dataclass(slots=True)
class GiftAward:
    promotion: GiftPromotion
    product: Product


def active_gift_promotions(db: Session, *, user_id: int, catalog_slug: str) -> list[GiftPromotion]:
    now = datetime.now(UTC).replace(tzinfo=None)
    redemption_count = (
        select(func.count(GiftPromotionRedemption.id))
        .where(
            GiftPromotionRedemption.promotion_id == GiftPromotion.id,
            GiftPromotionRedemption.user_id == user_id,
        )
        .correlate(GiftPromotion)
        .scalar_subquery()
    )
    stmt = (
        select(GiftPromotion)
        .options(
            selectinload(GiftPromotion.products),
            selectinload(GiftPromotion.gift_product).selectinload(Product.category),
        )
        .where(
            GiftPromotion.catalog_slug == catalog_slug,
            GiftPromotion.active.is_(True),
            or_(GiftPromotion.starts_at.is_(None), GiftPromotion.starts_at <= now),
            or_(GiftPromotion.ends_at.is_(None), GiftPromotion.ends_at >= now),
            redemption_count < GiftPromotion.max_redemptions_per_user,
        )
        .order_by(GiftPromotion.id)
    )
    return list(db.scalars(stmt).unique().all())


def qualifying_gifts(
    db: Session,
    *,
    user_id: int,
    catalog_slug: str,
    lines: Iterable[dict],
) -> list[GiftAward]:
    normalized = [
        {
            'ref': str(line.get('ref') or ''),
            'quantity': max(0, int(line.get('quantity') or 0)),
            'line_total': Decimal(str(line.get('line_total') or 0)),
        }
        for line in lines
    ]
    refs = [line['ref'] for line in normalized if line['ref']]
    brands_by_ref = {
        ref: str(brand or '').strip().casefold()
        for ref, brand in db.execute(select(Product.ref, Product.brand).where(Product.ref.in_(refs))).all()
    } if refs else {}
    awards: list[GiftAward] = []
    for promotion in active_gift_promotions(db, user_id=user_id, catalog_slug=catalog_slug):
        if promotion.eligibility_mode == 'brands':
            brands = {str(brand).strip().casefold() for brand in (promotion.eligible_brands_json or []) if str(brand).strip()}
            eligible = [line for line in normalized if brands_by_ref.get(line['ref'], '') in brands]
        else:
            eligible_refs = {link.product_ref for link in promotion.products}
            eligible = [line for line in normalized if line['ref'] in eligible_refs]
        if not eligible:
            continue
        if promotion.condition_type == 'value':
            reached = sum((line['line_total'] for line in eligible), Decimal('0')) >= Decimal(str(promotion.threshold_value or 0))
        else:
            reached = sum(line['quantity'] for line in eligible) >= int(promotion.threshold_quantity or 0)
        gift = promotion.gift_product
        if reached and gift is not None and gift.active and gift.manual_active and gift.catalog_slug == catalog_slug:
            awards.append(GiftAward(promotion=promotion, product=gift))
    return awards
