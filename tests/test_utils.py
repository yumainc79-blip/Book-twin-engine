from book_twin.utils import slugify


def test_slugify():
    assert slugify("Come essere stoici!") == "come_essere_stoici"
