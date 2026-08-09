from app.routes.v1.menu import get_menu


def test_get_menu():
    assert get_menu(1) is not None
