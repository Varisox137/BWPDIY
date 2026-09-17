import pytest

from bwpdiy.store import (
    SchemaError,
    StoreError,
    create_project,
    delete_card,
    delete_project,
    list_cards,
    list_projects,
    load_card,
    rename_project,
    save_card,
    validate_card,
)

SHIKIGAMI = {"type": "式神", "name": "山风", "faction": "红莲", "power": 3, "health": 4}
FIGHT = {
    "type": "战斗", "name": "斩", "level": 1, "rarity": "R",
    "shikigami": "山风", "power+": 1, "shield+": 1, "description": "测试。",
}
SPELL = {"type": "法术", "name": "烈", "level": 2, "rarity": "SR", "shikigami": "山风"}
FORM = {
    "type": "形态", "name": "突", "level": 2, "rarity": "SR",
    "shikigami": "山风", "power": 2, "health": 1,
}
FIELD = {"type": "幻境", "name": "鹤羽之佑", "rarity": "SSR", "shikigami": "山风", "durability": 6}
ASSIST = {"type": "协战", "name": "鸮羽共鸣", "rarity": "R", "shikigami": "山风"}


@pytest.fixture()
def lib(tmp_path):
    return tmp_path / "library"


# ---------- 项目 CRUD ----------

def test_create_and_list_projects(lib):
    create_project(lib, "山风")
    create_project(lib, "鸩")
    assert list_projects(lib) == ["山风", "鸩"]
    # 出厂骨架：cards/ + images/ + 默认式神卡
    assert (lib / "山风" / "cards").is_dir()
    assert (lib / "山风" / "images").is_dir()
    shikigami = load_card(lib, "山风", "shikigami")
    assert shikigami["type"] == "式神" and shikigami["name"] == "山风"


def test_list_projects_empty(lib):
    assert list_projects(lib) == []


def test_create_project_duplicate(lib):
    create_project(lib, "山风")
    with pytest.raises(StoreError, match="已存在"):
        create_project(lib, "山风")


def test_rename_project(lib):
    create_project(lib, "山风")
    save_card(lib, "山风", "斩", FIGHT)
    rename_project(lib, "山风", "岚")
    assert list_projects(lib) == ["岚"]
    assert load_card(lib, "岚", "斩") == FIGHT


def test_rename_project_errors(lib):
    create_project(lib, "山风")
    create_project(lib, "鸩")
    with pytest.raises(StoreError, match="不存在"):
        rename_project(lib, "无", "有")
    with pytest.raises(StoreError, match="已存在"):
        rename_project(lib, "山风", "鸩")


def test_delete_project(lib):
    create_project(lib, "山风")
    delete_project(lib, "山风")
    assert list_projects(lib) == []
    with pytest.raises(StoreError, match="不存在"):
        delete_project(lib, "山风")


# ---------- 名称安全 / 路径注入 ----------

@pytest.mark.parametrize("bad", [
    "", "  ", ".", "..", "../evil", "a/b", "a\\b", "a:b", "a*b", "a?b",
    'a"b', "a<b", "a>b", "a|b", "a..b/..", "尾点.", " 首尾空白", "首尾空白 ",
])
def test_project_name_injection_rejected(lib, bad):
    with pytest.raises(StoreError, match="项目名"):
        create_project(lib, bad)


@pytest.mark.parametrize("bad", ["", "..", "../x", "a/b", "a\\b", "a?b"])
def test_card_name_injection_rejected(lib, bad):
    create_project(lib, "山风")
    with pytest.raises(StoreError, match="卡名"):
        save_card(lib, "山风", bad, FIGHT)


def test_project_dir_not_escape(lib):
    create_project(lib, "山风")
    # 注入名即使已存在文件也不得命中
    (lib.parent / "evil.yaml").write_text("{}", encoding="utf-8")
    with pytest.raises(StoreError):
        load_card(lib, "山风", "../evil")


# ---------- 卡牌 CRUD ----------

def test_card_round_trip(lib):
    create_project(lib, "山风")
    save_card(lib, "山风", "斩", FIGHT)
    assert list_cards(lib, "山风") == ["shikigami", "斩"]
    assert load_card(lib, "山风", "斩") == FIGHT


def test_save_preserves_unicode_and_key_order(lib):
    create_project(lib, "山风")
    save_card(lib, "山风", "斩", FIGHT)
    text = (lib / "山风" / "cards" / "斩.yaml").read_text(encoding="utf-8")
    assert "斩" in text and "\\u" not in text  # 中文不转义
    keys = [line.split(":")[0] for line in text.splitlines() if line and not line.startswith(" ")]
    assert keys == list(FIGHT.keys())  # 键序稳定（插入序）


def test_load_card_missing(lib):
    create_project(lib, "山风")
    with pytest.raises(StoreError, match="不存在"):
        load_card(lib, "山风", "无此卡")


def test_load_card_invalid_yaml(lib):
    create_project(lib, "山风")
    (lib / "山风" / "cards" / "坏.yaml").write_text("- 这不是映射", encoding="utf-8")
    with pytest.raises(StoreError, match="yaml"):
        load_card(lib, "山风", "坏")


def test_delete_card(lib):
    create_project(lib, "山风")
    save_card(lib, "山风", "斩", FIGHT)
    delete_card(lib, "山风", "斩")
    assert list_cards(lib, "山风") == ["shikigami"]
    with pytest.raises(StoreError, match="不存在"):
        delete_card(lib, "山风", "斩")


def test_shikigami_card_cannot_be_deleted(lib):
    create_project(lib, "山风")
    with pytest.raises(StoreError, match="不可删除"):
        delete_card(lib, "山风", "shikigami")


def test_save_card_type_vs_location(lib):
    create_project(lib, "山风")
    # 式神卡只能存 shikigami.yaml
    with pytest.raises(SchemaError, match="式神"):
        save_card(lib, "山风", "山风", SHIKIGAMI)
    # shikigami.yaml 必须是式神卡
    with pytest.raises(SchemaError, match="式神"):
        save_card(lib, "山风", "shikigami", FIGHT)
    # 覆盖式神卡
    save_card(lib, "山风", "shikigami", SHIKIGAMI)
    assert load_card(lib, "山风", "shikigami") == SHIKIGAMI


def test_save_card_name_must_match_filename(lib):
    create_project(lib, "山风")
    with pytest.raises(SchemaError, match="name"):
        save_card(lib, "山风", "斩", {**FIGHT, "name": "突"})


def test_save_card_validates_schema(lib):
    create_project(lib, "山风")
    with pytest.raises(SchemaError) as exc:
        save_card(lib, "山风", "斩", {"type": "战斗", "name": "斩", "power": 1})
    assert "rarity" in str(exc.value) and "power" in str(exc.value)
    # 校验失败不落盘
    assert not (lib / "山风" / "cards" / "斩.yaml").exists()


# ---------- schema 校验：正例 ----------

@pytest.mark.parametrize("card", [
    SHIKIGAMI,
    FIGHT,
    SPELL,
    {**SPELL, "evolve": True, "power+": 1, "health+": -1},
    {**SPELL, "special_type": "衍生"},
    FORM,
    FIELD,
    ASSIST,
    {**FIGHT, "artwork": {"images": [
        {"path": "a.png"},
        {"path": "b.png", "offset_x": 0, "offset_y": -12, "scale": 1.15},
        {},
    ]}},
    {"type": "法术", "name": "最简", "rarity": "N"},
])
def test_validate_ok(card):
    assert validate_card(card) == []


# ---------- schema 校验：反例（消息含字段名） ----------

@pytest.mark.parametrize("card, needle", [
    ({"name": "x"}, "type"),
    ({**FIGHT, "type": "装备"}, "type"),
    ({**FIGHT, "name": ""}, "name"),
    ({**SHIKIGAMI, "faction": "黄金"}, "faction"),
    ({**FIGHT, "rarity": "UR"}, "rarity"),
    ({**FIGHT, "level": 4}, "level"),
    ({**FIGHT, "level": "1"}, "level"),
    ({**FIGHT, "evolve": "是"}, "evolve"),
    ({**SHIKIGAMI, "power": True}, "power"),          # bool 不算 int
    ({**SHIKIGAMI, "health": -1}, "health"),          # 非负
    ({**FIGHT, "power+": "1"}, "power+"),
    # 表外组合（stat 适用矩阵）
    ({**FIGHT, "power": 1}, "power"),                 # 战斗无裸 power
    ({**SPELL, "power+": 1}, "power+"),               # 非觉醒法术无 stat
    ({**FORM, "durability": 3}, "durability"),
    ({**FIELD, "health": 3}, "health"),
    ({**ASSIST, "power+": 1}, "power+"),
    ({**SHIKIGAMI, "level": 1}, "level"),             # 式神无等级
    ({**SHIKIGAMI, "rarity": "R"}, "rarity"),         # 式神无稀有度
    ({**FIGHT, "未知字段": 1}, "未知字段"),
    # artwork 结构形状
    ({**FIGHT, "artwork": []}, "artwork"),
    ({**FIGHT, "artwork": {"images": "a.png"}}, "images"),
    ({**FIGHT, "artwork": {"images": ["a.png"]}}, "images"),
    ({**FIGHT, "artwork": {"images": [{"path": 1}]}}, "path"),
    ({**FIGHT, "artwork": {"images": [{"offset_x": "左"}]}}, "offset_x"),
    ({**FIGHT, "artwork": {"images": [{"scale": 0}]}}, "scale"),
])
def test_validate_rejects(card, needle):
    errors = validate_card(card)
    assert errors, f"应判非法：{card}"
    assert any(needle in e for e in errors), errors


def test_validate_missing_required_shikigami():
    errors = validate_card({"type": "式神", "name": "x"})
    joined = "\n".join(errors)
    for field in ("faction", "power", "health"):
        assert field in joined


def test_validate_collects_multiple_errors():
    errors = validate_card({"type": "战斗", "name": "", "level": 9, "多余": 1})
    assert len(errors) >= 3  # 一次报全，不短路


def test_validate_not_a_mapping():
    assert validate_card(["不是映射"])
