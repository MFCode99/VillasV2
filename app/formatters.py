from __future__ import annotations

from datetime import datetime
from decimal import Decimal


def format_money(value: object) -> str:
    if value is None or value == '':
        return '-'
    if isinstance(value, Decimal):
        amount = value
    else:
        amount = Decimal(str(value))
    return f'{amount.quantize(Decimal("0.01")):f}'.replace('.', ',') + ' €'


def format_datetime(value: object) -> str:
    if value is None or value == '':
        return '-'
    if isinstance(value, datetime):
        return value.strftime('%d/%m/%Y %H:%M')
    return str(value)

