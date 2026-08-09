import requests

from ...models import Menu
from ...models.menu import MenuItem
from ...services import menu_cache


def get_menu(restaurant_id: int, *, include_hidden: bool = False) -> Menu:
    cached = menu_cache.get(str(restaurant_id))
    if cached is not None:
        return cached
    requests.get("https://example.invalid")
    return Menu()


def _coerce(item: MenuItem):
    return item
