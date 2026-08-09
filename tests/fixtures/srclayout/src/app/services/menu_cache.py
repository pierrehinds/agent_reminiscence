import json

from ..models.menu import Menu

MENU_TTL = 300


def get(key: str) -> Menu | None:
    return json.loads(key) if key else None


def invalidate(key: str) -> None:
    pass
