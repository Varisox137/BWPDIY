import pytest
import yaml

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
ASSIST = {"type": "协战", "name": "鸮羽共鸣", "rarity": "R", "shikigami1": "山风", "shikigami2": "薰"}


@pytest.fixture()
def lib(tmp_path):
    return tmp_path / "library"


# ---------- 项目 CRUD ----------

def test_create_and_list_projects(lib):
    create_project(lib, "山风")
    create_project(lib, "鸩")
    assert list_projects(lib) == ["山风", "鸩"]
    # 出厂骨架：空项目（cards/ + images/，无默认式神卡）
    assert (lib / "山风" / "cards").is_dir()
    assert (lib / "山风" / "images").is_dir()
    assert not (lib / "山风" / "shikigami.yaml").exists()
    assert list_cards(lib, "山风") == {"shikigami": [], "cards": []}


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


@pytest.mark.parametrize("bad", [
    "CON", "con", "PRN", "AUX", "NUL", "nul",
    "COM1", "com9", "LPT1", "lpt9", "con.txt",
])
def test_reserved_device_names_rejected(lib, bad):
    with pytest.raises(StoreError, match="保留"):
        create_project(lib, bad)


def test_rename_to_reserved_name(lib):
    create_project(lib, "山风")
    with pytest.raises(StoreError) as exc:
        rename_project(lib, "山风", "NUL")
    assert "保留" in str(exc.value)
    assert "已存在" not in str(exc.value)  # Windows 上 NUL.exists() 为真，不得误报


def test_card_name_reserved_rejected(lib):
    create_project(lib, "山风")
    with pytest.raises(StoreError, match="保留"):
        save_card(lib, "山风", "NUL", FIGHT)


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
    assert list_cards(lib, "山风") == {"shikigami": [], "cards": [{"stem": "斩", "name": "斩"}]}
    assert load_card(lib, "山风", "斩") == FIGHT


def test_list_cards_reads_name_and_sorts(lib):
    """列表 name 取自文件内容；各组按 name 排序，损坏/非映射文件 name=None 仍列出且排最后。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "10030701", FIGHT)          # name=斩
    save_card(lib, "山风", "10030702", SPELL)          # name=烈
    save_card(lib, "山风", "100307", SHIKIGAMI)        # name=山风
    (lib / "山风" / "cards" / "坏.yaml").write_text("- 这不是映射", encoding="utf-8")
    listed = list_cards(lib, "山风")
    assert listed["shikigami"] == [{"stem": "100307", "name": "山风"}]
    assert listed["cards"] == [
        {"stem": "10030701", "name": "斩"},
        {"stem": "10030702", "name": "烈"},
        {"stem": "坏", "name": None},
    ]


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


def test_load_card_broken_yaml_syntax(lib):
    create_project(lib, "山风")
    (lib / "山风" / "cards" / "坏.yaml").write_text("a: [未闭合", encoding="utf-8")
    with pytest.raises(StoreError, match="yaml"):
        load_card(lib, "山风", "坏")


def test_load_card_empty_file(lib):
    create_project(lib, "山风")
    (lib / "山风" / "cards" / "空.yaml").write_text("", encoding="utf-8")
    assert load_card(lib, "山风", "空") == {}


def test_rename_project_invalid_new_name(lib):
    create_project(lib, "山风")
    with pytest.raises(StoreError, match="项目名"):
        rename_project(lib, "山风", "../evil")
    assert list_projects(lib) == ["山风"]  # 未发生移动


def test_stat_matrix_parity_with_render():
    """store 与 render 双份 stat 适用矩阵键集/signed 口径对账（防漂移）。"""
    from bwpdiy.render.badges import _STAT_MATRIX
    from bwpdiy.store import schema

    store_keys = {(t, f) for t, fields in schema._STATS_BY_TYPE.items() for f in fields}
    assert store_keys == set(_STAT_MATRIX.keys())
    for (_ctype, field), mode in _STAT_MATRIX.items():
        assert (field in schema._SIGNED_STATS) == (mode == "signed"), field


def test_store_error_codes(lib):
    """StoreError 携带语义 code，供 web 层分派状态码（不依赖消息关键词）。"""
    with pytest.raises(StoreError) as e:
        create_project(lib, "../evil")
    assert e.value.code == "invalid_name"
    create_project(lib, "山风")
    with pytest.raises(StoreError) as e:
        create_project(lib, "山风")
    assert e.value.code == "already_exists"
    with pytest.raises(StoreError) as e:
        delete_project(lib, "无此项目")
    assert e.value.code == "not_found"
    with pytest.raises(StoreError) as e:
        load_card(lib, "山风", "无此卡")
    assert e.value.code == "not_found"
    (lib / "山风" / "cards" / "坏.yaml").write_text("a: [未闭合", encoding="utf-8")
    with pytest.raises(StoreError) as e:
        load_card(lib, "山风", "坏")
    assert e.value.code == "invalid_data"


def test_delete_card(lib):
    create_project(lib, "山风")
    save_card(lib, "山风", "斩", FIGHT)
    delete_card(lib, "山风", "斩")
    assert list_cards(lib, "山风")["cards"] == []
    with pytest.raises(StoreError, match="不存在"):
        delete_card(lib, "山风", "斩")


def test_shikigami_card_deletable(lib):
    """式神卡可删；引用它的卡保留失效字符串，不级联。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "100307", SHIKIGAMI)
    save_card(lib, "山风", "斩", FIGHT)
    delete_card(lib, "山风", "100307")
    assert list_cards(lib, "山风")["shikigami"] == []
    assert load_card(lib, "山风", "斩")["shikigami"] == "山风"  # 失效引用保留
    with pytest.raises(StoreError, match="不存在"):
        delete_card(lib, "山风", "100307")


def test_save_card_type_dispatches_directory(lib):
    """保存目录由 data["type"] 决定：式神 → shikigami/，其余 → cards/；stem 任意。"""
    create_project(lib, "山风")
    path, updated = save_card(lib, "山风", "100307", SHIKIGAMI)
    assert path == lib / "山风" / "shikigami" / "100307.yaml"
    assert updated == []
    path, _ = save_card(lib, "山风", "10030701", FIGHT)
    assert path == lib / "山风" / "cards" / "10030701.yaml"
    # 同名文件已存在于另一目录（类型与目录不符）→ 报错指引
    with pytest.raises(StoreError, match="与卡牌类型不符"):
        save_card(lib, "山风", "100307", {**FIGHT, "shikigami": "山风"})
    assert load_card(lib, "山风", "100307") == SHIKIGAMI  # 未被覆盖


def test_save_card_name_ne_stem(lib):
    """name==文件名强制校验已删除：文件名任意，卡名以文件内容为准。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "10030701", {**FIGHT, "name": "突"})
    assert load_card(lib, "山风", "10030701")["name"] == "突"
    listed = list_cards(lib, "山风")["cards"]
    assert listed == [{"stem": "10030701", "name": "突"}]


def test_save_card_validates_schema(lib):
    create_project(lib, "山风")
    with pytest.raises(SchemaError) as exc:
        save_card(lib, "山风", "斩", {"type": "战斗", "name": "斩", "power": 1})
    assert "rarity" in str(exc.value) and "power" in str(exc.value)
    # 校验失败不落盘
    assert not (lib / "山风" / "cards" / "斩.yaml").exists()


# ---------- 数量上限 / 式神名唯一 / 改名联动 ----------

def test_max_cards_limit(lib, monkeypatch):
    """非式神卡新增超 MAX_CARDS 拒绝（覆盖已有卡不计入）；式神卡不占额度。"""
    import bwpdiy.store.projects as projects

    monkeypatch.setattr(projects, "MAX_CARDS", 2)
    create_project(lib, "山风")
    save_card(lib, "山风", "100307", SHIKIGAMI)          # 式神卡不计入
    save_card(lib, "山风", "斩", FIGHT)
    save_card(lib, "山风", "烈", SPELL)
    save_card(lib, "山风", "斩", {**FIGHT, "power+": 2})  # 覆盖已有卡不计入
    with pytest.raises(StoreError, match="上限") as exc:
        save_card(lib, "山风", "突", FORM)
    assert exc.value.code == "forbidden"
    assert not (lib / "山风" / "cards" / "突.yaml").exists()


def test_shikigami_name_unique(lib):
    """式神卡 name 全项目唯一（引用按名关联，必须无歧义）。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "100307", SHIKIGAMI)
    with pytest.raises(SchemaError, match="唯一"):
        save_card(lib, "山风", "200307", {**SHIKIGAMI, "name": "山风"})
    # 同名覆盖自身（同 stem）不冲突
    save_card(lib, "山风", "100307", {**SHIKIGAMI, "power": 4})
    assert load_card(lib, "山风", "100307")["power"] == 4


def test_rename_shikigami_cascades(lib):
    """式神改名联动：其余卡的 shikigami/shikigami1/shikigami2 引用同步改写。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "100307", SHIKIGAMI)
    save_card(lib, "山风", "100816", {**SHIKIGAMI, "name": "薰"})
    save_card(lib, "山风", "斩", FIGHT)                              # shikigami: 山风
    save_card(lib, "山风", "鸮羽共鸣", ASSIST)                       # shikigami1: 山风
    save_card(lib, "山风", "烈", SPELL)                              # shikigami: 山风
    renamed = {**SHIKIGAMI, "name": "岚"}
    _, updated = save_card(lib, "山风", "100307", renamed)
    assert sorted(updated) == ["斩", "烈", "鸮羽共鸣"]
    assert load_card(lib, "山风", "斩")["shikigami"] == "岚"
    assert load_card(lib, "山风", "烈")["shikigami"] == "岚"
    assist = load_card(lib, "山风", "鸮羽共鸣")
    assert assist["shikigami1"] == "岚" and assist["shikigami2"] == "薰"  # 只改命中的引用
    # 未改名再保存：无联动
    _, updated = save_card(lib, "山风", "100307", renamed)
    assert updated == []


def test_rename_cascade_only_for_shikigami(lib):
    """非式神卡保存（即使改了自身 name）不触发引用联动。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "100307", SHIKIGAMI)
    save_card(lib, "山风", "斩", FIGHT)
    _, updated = save_card(lib, "山风", "斩", {**FIGHT, "name": "斩改"})
    assert updated == []
    assert load_card(lib, "山风", "100307") == SHIKIGAMI


# ---------- schema 校验：正例 ----------

@pytest.mark.parametrize("card", [
    SHIKIGAMI,
    FIGHT,
    SPELL,
    {**SPELL, "evolve": True, "power+": 1, "health+": -1},
    {**FIGHT, "evolve": True},                          # 战斗可觉醒
    {**FORM, "evolve": True},                           # 形态可觉醒
    {**FIELD, "evolve": True},                          # 幻境可觉醒
    {**SPELL, "special_type": "衍生"},
    {**FIGHT, "frame_variant": "norm"},                 # 框品：战斗可携带
    {**SPELL, "frame_variant": "blue"},                 # 琉璃
    {**FORM, "frame_variant": "black"},                 # 墨染
    {**FIELD, "frame_variant": "red"},                  # 百炼
    {**SHIKIGAMI, "frame_variant": "black"},            # 式神可携带（牌框同形态）
    FORM,
    FIELD,
    ASSIST,
    {**FIGHT, "artwork": {"images": [
        {"path": "a.png"},
        {"path": "b.png", "offset_x": 0, "offset_y": -12, "scale": 1.15, "rotate": 30},
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
    ({**ASSIST, "evolve": True}, "evolve"),             # 协战不可觉醒（白名单之外）
    ({**ASSIST, "shikigami": "山风"}, "shikigami"),     # 协战用 shikigami1/shikigami2，不收 shikigami
    ({**FIGHT, "shikigami1": "山风"}, "shikigami1"),    # 双式神引用为协战专属
    ({**ASSIST, "shikigami1": 1}, "shikigami1"),        # 引用必须是字符串
    ({**SHIKIGAMI, "evolve": True}, "evolve"),          # 式神不可觉醒
    ({**FIGHT, "frame_variant": "gold"}, "frame_variant"),   # 非法框品
    ({**FIGHT, "frame_variant": 1}, "frame_variant"),
    ({**ASSIST, "frame_variant": "blue"}, "frame_variant"),     # 协战无框品（白名单之外）
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
    ({**FIGHT, "artwork": {"images": [{"rotate": "九十"}]}}, "rotate"),
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
