from .pricing import price_of

__all__ = ["Menu", "MenuItem"]

SCHEMA_VERSION = 3


class MenuItem:
    pass


class Menu:
    def total(self):
        return price_of(self)


def _internal():
    pass
