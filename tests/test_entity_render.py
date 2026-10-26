import math

import pytest
from PIL import ImageChops

from bwpdiy.render import entity_eligible, render_entity, validate_entity_state
from bwpdiy.render.assets import get_library


def make_card(sample_art, **kw):
    card = {
        "type": "式神",
        "name": "sample_art",
        "level": 2,
        "_base_dir": str(sample_art.parent),
        "artwork": {"images": [{"path": sample_art.name}]},
    }
    card.update(kw)
    return card


def images_equal(left, right):
    return (left.size == right.size
            and ImageChops.difference(left.convert("RGB"), right.convert("RGB")).getbbox() is None)


@pytest.mark.parametrize("card, expected", [
    ({"type": "式神"}, True),
    ({"type": "形态"}, True),
    ({"type": "法术", "evolve": True}, True),
    ({"type": "战斗", "evolve": True}, True),
    ({"type": "战斗"}, False),
    ({"type": "法术", "evolve": False}, False),
    ({"type": "法术", "evolve": 1}, False),
    ({}, False),
])
def test_entity_eligible(card, expected):
    assert entity_eligible(card) is expected


def test_validate_entity_state_defaults_and_discards_unknown_keys():
    state = {"power": 2, "unknown": "discard"}
    original = dict(state)
    assert validate_entity_state(state) == {
        "level": 1,
        "level_color": "yellow",
        "power": 2,
        "health": 0,
        "combat_power": 0,
        "shield": 0,
        "art_scale": 1.0,
    }
    assert state == original


@pytest.mark.parametrize("field, value", [
    ("power", True), ("health", False),
    ("combat_power", True), ("shield", False),
    ("level", True), ("art_scale", True),
    ("power", -1), ("health", -1),
    ("power", 1.5), ("health", "2"),
    ("combat_power", 1.5), ("shield", "2"),
    ("level", 0), ("level", 4), ("level", 1.0),
    ("level_color", "orange"), ("level_color", None),
    ("art_scale", 0), ("art_scale", -1),
    ("art_scale", math.nan), ("art_scale", math.inf),
    ("art_scale", "2"),
])
def test_validate_entity_state_rejects_invalid_values(field, value):
    with pytest.raises(ValueError):
        validate_entity_state({field: value})


def test_validate_entity_state_rejects_non_mapping():
    with pytest.raises(ValueError):
        validate_entity_state([])


def test_entity_native_size_and_zero_stats(assets_dir, sample_art, monkeypatch):
    import bwpdiy.render.entity as entity

    card = make_card(sample_art)
    state = {"power": 0, "health": 0, "combat_power": 0, "shield": 0}
    lib = get_library(assets_dir)
    badges = []
    original_badge = lib.stat_badge
    monkeypatch.setattr(lib, "stat_badge",
                        lambda name: badges.append(name) or original_badge(name))
    digits = []
    original_digits = entity._render_digits
    monkeypatch.setattr(entity, "_render_digits",
                        lambda text, *args: digits.append(text) or original_digits(text, *args))

    image = render_entity(card, state, assets_dir, crop=False)

    assert image.size == (64, 96)
    assert image.mode == "RGBA"
    assert "power" in badges and "health" in badges
    assert digits == ["0", "0"]


@pytest.mark.parametrize("value, expected", [
    (2, "combat_power"),
    (-2, "weak"),
    (0, None),
])
def test_entity_combat_power_picks_icon(assets_dir, sample_art, monkeypatch,
                                       value, expected):
    lib = get_library(assets_dir)
    names = []
    original = lib.icon
    monkeypatch.setattr(lib, "icon", lambda name: names.append(name) or original(name))
    render_entity(make_card(sample_art, type="形态"),
                  {"combat_power": value}, assets_dir)
    combat_icons = [name for name in names if name in ("combat_power", "weak")]
    assert combat_icons == ([expected] if expected else [])


@pytest.mark.parametrize("value, expected", [
    (3, "combat_shield"),
    (-3, "combat_fragile_2"),
    (0, None),
])
def test_entity_shield_picks_badge(assets_dir, sample_art, monkeypatch,
                                  value, expected):
    lib = get_library(assets_dir)
    names = []
    original = lib.stat_badge
    monkeypatch.setattr(lib, "stat_badge",
                        lambda name: names.append(name) or original(name))
    render_entity(make_card(sample_art, type="形态"), {"shield": value}, assets_dir)
    shields = [name for name in names
               if name in ("combat_shield", "combat_fragile_2")]
    assert shields == ([expected] if expected else [])


def test_entity_signed_modifiers_pick_icons(assets_dir, sample_art, monkeypatch):
    card = make_card(sample_art, type="形态")
    lib = get_library(assets_dir)
    names = []
    original = lib.icon
    monkeypatch.setattr(lib, "icon", lambda name: names.append(name) or original(name))
    render_entity(card, {"combat_power": -2, "shield": 3}, assets_dir)
    assert "weak" in names and "shield" not in names


@pytest.mark.parametrize("color", ["yellow", "cyan", "purple", "red", "blue", "brown"])
def test_entity_level_colors(assets_dir, sample_art, monkeypatch, color):
    lib = get_library(assets_dir)
    calls = []
    original = lib.level_num
    monkeypatch.setattr(lib, "level_num",
                        lambda n, c="yellow": calls.append((n, c)) or original(n, c))
    monkeypatch.setattr(lib, "level_star",
                        lambda: pytest.fail("对局式神不得绘制觉醒星"))
    render_entity(make_card(sample_art),
                  {"level": 3, "level_color": color}, assets_dir)
    assert calls == [(3, color)]


@pytest.mark.parametrize("card_level, card_color, expected", [
    (2, "cyan", (2, "cyan")),
    (9, "orange", (1, "yellow")),
    (None, None, (1, "yellow")),
])
def test_entity_level_defaults_come_from_valid_card_values(
        assets_dir, sample_art, monkeypatch, card_level, card_color, expected):
    lib = get_library(assets_dir)
    calls = []
    original = lib.level_num
    monkeypatch.setattr(lib, "level_num",
                        lambda n, c="yellow": calls.append((n, c)) or original(n, c))
    render_entity(make_card(sample_art, level=card_level, level_color=card_color),
                  {}, assets_dir)
    assert calls == [expected]


@pytest.mark.parametrize("source", ["state", "card"])
def test_entity_non_string_level_color_handling(assets_dir, sample_art, source):
    if source == "state":
        with pytest.raises(ValueError):
            render_entity(make_card(sample_art), {"level_color": []}, assets_dir)
        return
    invalid = render_entity(make_card(sample_art, level_color=[]), {}, assets_dir)
    fallback = render_entity(make_card(sample_art, level_color=None), {}, assets_dir)
    assert images_equal(invalid, fallback)


def test_entity_art_scale_replaces_source_scale_and_maps_offsets(
        assets_dir, sample_art, monkeypatch):
    import bwpdiy.render.entity as entity

    source = {"path": sample_art.name, "scale": 99,
              "offset_x": 128, "offset_y": -64}
    card = make_card(sample_art, artwork={"images": [source]})
    calls = []
    original = entity.fit_artwork

    def capture(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(entity, "fit_artwork", capture)
    scaled = render_entity(card, {"art_scale": 2}, assets_dir, crop=False)
    args, kwargs = calls[-1]
    inner_size = args[1]
    assert args[2] == 128 * inner_size[0] / 512
    assert args[3] == -64 * inner_size[0] / 512
    assert args[4] == 2
    assert kwargs["cover_base"] is not None

    card["artwork"]["images"][0]["scale"] = 1
    unscaled = render_entity(card, {"art_scale": 2}, assets_dir, crop=False)
    assert images_equal(scaled, unscaled)
    smaller = render_entity(card, {"art_scale": 1}, assets_dir, crop=False)
    assert not images_equal(scaled, smaller)


@pytest.mark.parametrize("ref", [
    {"offset_x": 40},
    {"offset_y": -30},
    {"rotate": 37},
])
def test_entity_inherits_source_offset_and_rotation(assets_dir, sample_art, ref):
    base = make_card(sample_art)
    changed = make_card(sample_art, artwork={"images": [
        {"path": sample_art.name, **ref},
    ]})
    assert not images_equal(render_entity(base, {}, assets_dir, crop=False),
                            render_entity(changed, {}, assets_dir, crop=False))


def test_entity_crop_is_tight_and_reports_origin(assets_dir, sample_art):
    card = make_card(sample_art)
    full = render_entity(card, {}, assets_dir, crop=False)
    alpha = full.getchannel("A").point(lambda value: 255 if value > 10 else 0)
    bbox = alpha.getbbox()
    assert bbox is not None
    info = {}
    cropped = render_entity(card, {}, assets_dir, crop=True, info=info)
    assert cropped.size == (bbox[2] - bbox[0], bbox[3] - bbox[1])
    assert info["crop_origin"] == bbox[:2]
    cropped_alpha = cropped.getchannel("A").point(lambda value: 255 if value > 10 else 0)
    assert cropped_alpha.getbbox() == (0, 0, cropped.width, cropped.height)


def test_entity_rejects_ineligible_source(assets_dir, sample_art):
    with pytest.raises(ValueError, match="不支持"):
        render_entity(make_card(sample_art, type="战斗"), {}, assets_dir)


def test_entity_artwork_path_escape_rejected(assets_dir, sample_art):
    card = make_card(sample_art, artwork={"images": [{"path": "../outside.png"}]})
    with pytest.raises(ValueError, match="越出基准目录"):
        render_entity(card, {}, assets_dir)
