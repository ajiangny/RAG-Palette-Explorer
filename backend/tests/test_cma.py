import pytest

from ingest.cma import artist_name, exclusion_reason


@pytest.mark.parametrize("title, excluded", [
    ("Text, Folio 32 (verso), from a Kalpa-sutra", True),
    ("Text: Folio 2 (verso), from a Kalpa-sutra", True),
    ("Text of Rustam and Suhrab, from the Shah-nama of Firdausi", True),
    ("Page from a Tuti-nama: The Parrot", False),
    ("Textile Merchant", False),
    ("Portrait of a Man", False),
])
def test_text_pages_are_excluded_but_not_illustrated_pages(title, excluded):
    assert (exclusion_reason(title) is not None) == excluded


def test_artist_name_drops_nationality_and_dates():
    assert artist_name([{"description": "Claude Monet (French, 1840–1926)", "role": "artist"}]) == "Claude Monet"
    assert artist_name([]) is None
