import pytest

from ingest.nga import exclusion_reason, iiif_url, select_rows


def obj(objectid="1", classification="Painting", isvirtual="0", title="Saint Paul", attribution="Bernardo Daddi"):
    return {"objectid": objectid, "classification": classification, "isvirtual": isvirtual, "title": title,
            "attribution": attribution, "displaydate": "1333"}


def img(objectid="1", viewtype="primary", openaccess="1", width="3000"):
    return {"depictstmsobjectid": objectid, "viewtype": viewtype, "openaccess": openaccess, "width": width,
            "iiifurl": "https://api.nga.gov/iiif/abc"}


@pytest.mark.parametrize("title, excluded", [
    ("Christ on the Cross [reverse]", True),
    ("Indian Tobacco Shop Sign [reverse, Indian facing right]", True),
    ("Saint Andrew [left panel]", False),
    ("The Reverse of Fortune", False),
])
def test_panel_backs_are_excluded(title, excluded):
    assert (exclusion_reason(title) is not None) == excluded


def test_only_open_access_primary_images_of_real_paintings_are_selected():
    assert [r["source_id"] for r in select_rows([obj()], [img()])] == ["1"]
    assert select_rows([obj()], [img(openaccess="0")]) == []
    assert select_rows([obj()], [img(viewtype="alternate")]) == []
    assert select_rows([obj(classification="Print")], [img()]) == []
    assert select_rows([obj(isvirtual="1")], [img()]) == []


def test_images_are_never_upscaled():
    assert iiif_url(img(width="3000"), 400).endswith("/full/400,/0/default.jpg")
    assert iiif_url(img(width="250"), 400).endswith("/full/250,/0/default.jpg")
    assert iiif_url(img(width=""), 400).endswith("/full/400,/0/default.jpg")


def test_missing_artist_is_null_not_empty():
    assert select_rows([obj(attribution="")], [img()])[0]["artist"] is None
