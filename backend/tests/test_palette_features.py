import numpy as np
import pytest
from PIL import Image
from skimage.color import rgb2lab

from app.features import HistConfig, image_histogram, lab_histogram
from app.palette import extract_palette, lab_to_hex, load_lab


def solid(rgb: tuple[int, int, int], size=(64, 48)) -> Image.Image:
    return Image.new("RGB", size, rgb)


def two_color(a, b, frac_a: float, size=(100, 100)) -> Image.Image:
    arr = np.empty((size[1], size[0], 3), dtype=np.uint8)
    split = int(size[1] * frac_a)
    arr[:split] = a
    arr[split:] = b
    return Image.fromarray(arr)


def test_load_lab_downscales():
    lab = load_lab(solid((10, 20, 30), size=(800, 400)), max_side=200)
    assert lab.shape == (200 * 100, 3)


def test_solid_image_gives_single_color():
    palette = extract_palette(solid((200, 30, 40)))
    assert len(palette) == 1
    assert palette[0]["weight"] == pytest.approx(1.0)
    assert palette[0]["hex"] == "#c81e28"


def test_two_color_weights_and_order():
    palette = extract_palette(two_color((0, 0, 255), (255, 255, 0), frac_a=0.7), k=6)
    assert [s["hex"] for s in palette] == ["#0000ff", "#ffff00"]
    assert palette[0]["weight"] == pytest.approx(0.7, abs=0.01)
    assert sum(s["weight"] for s in palette) == pytest.approx(1.0, abs=1e-3)


def test_palette_respects_k_and_weights_sum_to_one():
    rng = np.random.default_rng(0)
    noisy = Image.fromarray(rng.integers(0, 256, (80, 80, 3), dtype=np.uint8))
    palette = extract_palette(noisy, k=5)
    assert len(palette) == 5
    weights = [s["weight"] for s in palette]
    assert weights == sorted(weights, reverse=True)
    assert sum(weights) == pytest.approx(1.0, abs=1e-3)


def test_lab_to_hex_roundtrip():
    lab = rgb2lab(np.array([[[18 / 255, 52 / 255, 86 / 255]]])).reshape(3)
    assert lab_to_hex(lab) == "#123456"


def test_histogram_sums_to_one_without_hellinger():
    cfg = HistConfig(hellinger=False)
    h = image_histogram(two_color((0, 0, 255), (255, 255, 0), 0.5), cfg)
    assert h.shape == (512,)
    assert h.sum() == pytest.approx(1.0)
    assert np.count_nonzero(h) == 2


def test_hellinger_histogram_has_unit_l2_norm():
    h = image_histogram(two_color((10, 120, 30), (240, 240, 240), 0.3))
    assert np.linalg.norm(h) == pytest.approx(1.0)


def test_solid_image_fills_one_bin_and_config_sets_dim():
    cfg = HistConfig(bins=(4, 6, 6))
    h = image_histogram(solid((90, 90, 90)), cfg)
    assert h.shape == (cfg.dim,) == (144,)
    assert np.count_nonzero(h) == 1


def test_out_of_range_ab_is_clipped_not_dropped():
    lab = np.array([[50.0, 127.0, -127.0], [50.0, 0.0, 0.0]])
    h = lab_histogram(lab, HistConfig(hellinger=False))
    assert h.sum() == pytest.approx(1.0)


def test_transparent_pixels_are_ignored():
    arr = np.zeros((10, 10, 4), dtype=np.uint8)
    arr[:5] = (200, 30, 40, 255)  # top half opaque red, bottom half fully transparent black
    palette = extract_palette(Image.fromarray(arr, "RGBA"))
    assert [s["hex"] for s in palette] == ["#c81e28"]
    assert load_lab(Image.fromarray(arr, "RGBA")).shape == (50, 3)


def test_fully_transparent_image_is_rejected():
    with pytest.raises(OSError):
        load_lab(Image.new("RGBA", (20, 20), (0, 0, 0, 0)))
