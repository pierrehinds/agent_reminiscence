import decimal

from .menu import MenuItem

TAX_RATE = decimal.Decimal("0.2")


def price_of(item: MenuItem):
    return TAX_RATE


def _round(value):
    return value
