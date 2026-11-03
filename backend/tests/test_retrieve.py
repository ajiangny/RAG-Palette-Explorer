import contextlib
import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from skimage.color import rgb2lab

import app.main
import app.retrieve
from app.retrieve import palette_distance, palette_similarity, rerank


def swatch(rgb, weight):
    lab = rgb2lab(np.array([[rgb]], dtype=np.float64) / 255).reshape(3)
    return {"lab": lab.tolist(), "hex": "#000000", "weight": weight}


RED, ORANGE, BLUE, NAVY = (200, 30, 30), (220, 110, 30), (30, 60, 200), (20, 30, 90)


def test_identical_palettes_have_zero_distance():
    p = [swatch(RED, 0.6), swatch(BLUE, 0.4)]
    assert palette_distance(p, p) == pytest.approx(0, abs=1e-6)


def test_distance_ignores_swatch_order_and_is_symmetric():
    p = [swatch(RED, 0.6), swatch(BLUE, 0.4)]
    q = [swatch(BLUE, 0.3), swatch(ORANGE, 0.7)]
    assert palette_distance(p, q) == pytest.approx(palette_distance(q, p), rel=1e-6)
    assert palette_distance(p, p[::-1]) == pytest.approx(0, abs=1e-6)


def test_closer_colors_give_smaller_distance():
    query = [swatch(RED, 1.0)]
    assert palette_distance(query, [swatch(ORANGE, 1.0)]) < palette_distance(query, [swatch(BLUE, 1.0)])


def test_weights_matter():
    # Same two colors, but proportions flipped → nonzero distance that grows with the imbalance.
    p = [swatch(RED, 0.9), swatch(BLUE, 0.1)]
    q_mild = [swatch(RED, 0.7), swatch(BLUE, 0.3)]
    q_flip = [swatch(RED, 0.1), swatch(BLUE, 0.9)]
    assert 0 < palette_distance(p, q_mild) < palette_distance(p, q_flip)


def test_single_color_distance_equals_ciede2000():
    from skimage.color import deltaE_ciede2000
    a, b = swatch(RED, 1.0), swatch(NAVY, 1.0)
    expected = deltaE_ciede2000(np.array(a["lab"]), np.array(b["lab"]))
    assert palette_distance([a], [b]) == pytest.approx(expected, rel=1e-6)


def test_palettes_of_different_sizes():
    p = [swatch(RED, 0.5), swatch(BLUE, 0.5)]
    q = [swatch(RED, 0.25), swatch(RED, 0.25), swatch(BLUE, 0.5)]
    assert palette_distance(p, q) == pytest.approx(0, abs=1e-6)


def test_rerank_orders_by_palette_and_blends_with_alpha():
    query = [swatch(RED, 1.0)]
    candidates = [
        {"id": 1, "palette": [swatch(BLUE, 1.0)], "hist_similarity": 0.99},
        {"id": 2, "palette": [swatch(ORANGE, 1.0)], "hist_similarity": 0.10},
        {"id": 3, "palette": [swatch(RED, 1.0)], "hist_similarity": 0.50},
    ]
    assert [c["id"] for c in rerank(query, candidates, k=3, alpha=0.0)] == [3, 2, 1]
    assert [c["id"] for c in rerank(query, candidates, k=3, alpha=1.0)] == [1, 3, 2]
    top = rerank(query, candidates, k=1, alpha=0.0)
    assert len(top) == 1 and top[0]["score"] == pytest.approx(palette_similarity(0), abs=1e-3)
    # Default blend: an exact palette match with middling histogram similarity still wins.
    assert rerank(query, candidates, k=1)[0]["id"] == 3


def png_bytes(rgb) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), rgb).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def client(monkeypatch):
    candidates = [
        {"id": i, "aic_id": i, "title": f"t{i}", "artist": "a", "image_url": "u",
         "palette": [swatch(c, 1.0)], "hist_similarity": 0.5}
        for i, c in enumerate([BLUE, RED, ORANGE, NAVY])
    ]
    monkeypatch.setattr(app.main, "connect", lambda: contextlib.nullcontext(None))
    monkeypatch.setattr(app.retrieve, "stage1", lambda conn, hist, n: candidates[:n])
    return TestClient(app.main.app)


def test_match_endpoint(client):
    r = client.post("/match?k=2", files={"file": ("red.png", png_bytes(RED), "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert body["query_palette"][0]["hex"] == "#c81e1e"
    assert [m["id"] for m in body["results"]] == [1, 2]


def test_match_rejects_non_image(client):
    r = client.post("/match", files={"file": ("x.txt", b"not an image", "text/plain")})
    assert r.status_code == 400


def test_ab_metrics_ignore_lightness_and_kl2_discounts_it():
    dark, light = [swatch((60, 60, 60), 1.0)], [swatch((200, 200, 200), 1.0)]
    assert palette_distance(dark, light, "ab") == pytest.approx(0, abs=0.5)
    assert palette_distance(dark, light, "de2000_kL2") == pytest.approx(palette_distance(dark, light) / 2, rel=0.01)


def test_chroma_penalty_separates_muted_from_saturated():
    vivid, muted = [swatch((220, 30, 30), 1.0)], [swatch((150, 110, 110), 1.0)]
    assert palette_distance(vivid, muted, "ab+chroma") > palette_distance(vivid, muted, "ab")


def test_unknown_metric_is_rejected():
    with pytest.raises(ValueError):
        palette_distance([swatch(RED, 1.0)], [swatch(BLUE, 1.0)], "nope")


def test_match_rejects_fully_transparent_image(client):
    buf = io.BytesIO()
    Image.new("RGBA", (40, 40), (0, 0, 0, 0)).save(buf, format="PNG")
    r = client.post("/match", files={"file": ("blank.png", buf.getvalue(), "image/png")})
    assert r.status_code == 400
