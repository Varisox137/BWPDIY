from datetime import date
from pathlib import Path

import pytest
import yaml

from bwpdiy.store import (
    SchemaError,
    StoreError,
    create_project,
    delete_card,
    delete_mechanism,
    delete_project,
    list_cards,
    list_mechanisms,
    list_projects,
    load_card,
    load_mechanism,
    rename_project,
    save_card,
    save_mechanism,
    validate_card,
    validate_mechanism,
)

TODAY = date.today().strftime("%Y%m%d")


def with_today(card):
    """保存时 version_date 留空填当前系统日期：读回比对统一附带。"""
    return {**card, "version_date": TODAY}


def entry(stem, name, cid=None, vd=TODAY, shiki=None, stats=False, rarity="R", ctype=None):
    """单版本分组条目（list_cards/list_mechanisms 口径；stats=附式神基础值）。"""
    version = {"stem": stem, "date": vd}
    if shiki is not None or stats:
        version.update(type=ctype or ("式神" if stats else "战斗"),
                       rarity=None if stats else rarity, shikigami=shiki,
                       shikigami1=None, shikigami2=None)
    data = {"stem": stem, "name": name, "id": cid,
            "versions": [version], "count": 1,
            "shikigami": shiki, "shikigami1": None, "shikigami2": None}
    if stats:
        data.update(power=3, health=4)
    return data


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
    assert load_card(lib, "岚", "斩") == with_today(FIGHT)


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


@pytest.mark.parametrize("reserved", ["mechanisms", "Mechanisms", "MECHANISMS"])
def test_mechanisms_project_name_rejected_everywhere(lib, reserved):
    """共享机制目录保留名不区分大小写，且删除等路径操作也不能绕过。"""
    create_project(lib, "山风")
    shared = lib / "mechanisms"
    shared.mkdir()
    keep = shared / "keep.yaml"
    keep.write_text("name: 保留机制", encoding="utf-8")
    with pytest.raises(StoreError, match="机制共享池保留目录名"):
        create_project(lib, reserved)
    with pytest.raises(StoreError, match="机制共享池保留目录名"):
        rename_project(lib, "山风", reserved)
    with pytest.raises(StoreError, match="机制共享池保留目录名"):
        delete_project(lib, reserved)
    assert keep.is_file() and list_projects(lib) == ["山风"]


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
    assert list_cards(lib, "山风") == {"shikigami": [], "cards": [entry("斩", "斩", shiki="山风")]}
    assert load_card(lib, "山风", "斩") == with_today(FIGHT)


def test_list_cards_reads_name_and_sorts(lib):
    """列表 name 取自文件内容；各组按 name 排序，损坏/非映射文件 name=None 仍列出且排最后。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "10030701", FIGHT)          # name=斩
    save_card(lib, "山风", "10030702", SPELL)          # name=烈
    save_card(lib, "山风", "100307", SHIKIGAMI)        # name=山风
    (lib / "山风" / "cards" / "坏.yaml").write_text("- 这不是映射", encoding="utf-8")
    listed = list_cards(lib, "山风")
    assert listed["shikigami"] == [entry("100307", "山风", stats=True)]
    assert listed["cards"] == [
        entry("10030701", "斩", shiki="山风"),
        entry("10030702", "烈", shiki="山风", rarity="SR", ctype="法术"),
        entry("坏", None, vd=""),
    ]


def test_save_preserves_unicode_and_key_order(lib):
    create_project(lib, "山风")
    save_card(lib, "山风", "斩", FIGHT)
    text = (lib / "山风" / "cards" / "斩.yaml").read_text(encoding="utf-8")
    assert "斩" in text and "\\u" not in text  # 中文不转义
    keys = [line.split(":")[0] for line in text.splitlines() if line and not line.startswith(" ")]
    assert keys == [*FIGHT.keys(), "version_date"]  # 键序稳定（插入序；日期保存时追加）


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
    assert load_card(lib, "山风", "100307") == with_today(SHIKIGAMI)  # 未被覆盖


def test_save_card_name_ne_stem(lib):
    """name==文件名强制校验已删除：文件名任意，卡名以文件内容为准。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "10030701", {**FIGHT, "name": "突"})
    assert load_card(lib, "山风", "10030701")["name"] == "突"
    listed = list_cards(lib, "山风")["cards"]
    assert listed == [entry("10030701", "突", shiki="山风")]


def test_save_card_validates_schema(lib):
    create_project(lib, "山风")
    with pytest.raises(SchemaError) as exc:
        save_card(lib, "山风", "斩", {"type": "战斗", "name": "斩", "power": 1})
    assert "power" in str(exc.value)
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


def test_max_shikigami_limit(lib, monkeypatch):
    """式神卡新增超 MAX_SHIKIGAMI 拒绝（覆盖已有卡不计入）。"""
    import bwpdiy.store.projects as projects

    monkeypatch.setattr(projects, "MAX_SHIKIGAMI", 2)
    create_project(lib, "山风")
    save_card(lib, "山风", "100307", SHIKIGAMI)
    save_card(lib, "山风", "100308", {**SHIKIGAMI, "name": "薰"})
    save_card(lib, "山风", "100307", {**SHIKIGAMI, "power": 4})  # 覆盖已有卡不计入
    with pytest.raises(StoreError, match="式神上限") as exc:
        save_card(lib, "山风", "100309", {**SHIKIGAMI, "name": "辉夜姬"})
    assert exc.value.code == "forbidden"
    assert not (lib / "山风" / "shikigami" / "100309.yaml").exists()


def test_shikigami_name_unique(lib):
    """式神卡 name 全项目唯一（引用按名关联）；同 id+卡名的多版本同名允许。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "100307", SHIKIGAMI)
    with pytest.raises(SchemaError, match="唯一"):
        save_card(lib, "山风", "200307", {**SHIKIGAMI, "id": "200307"})  # 跨组同名拒绝
    # 同组（id+name 均相同）另一文件：视作多版本，允许
    save_card(lib, "山风", "100307@20260102", with_today(SHIKIGAMI))
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
    assert load_card(lib, "山风", "100307") == with_today(SHIKIGAMI)


def test_rename_card_renames_file_without_id(lib):
    """无 id 且文件按卡名回退命名（stem == 旧卡名）：改名同步重命名 yaml。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "斩", FIGHT)
    path, _ = save_card(lib, "山风", "斩", {**FIGHT, "name": "斩改"})
    assert path.name == "斩改.yaml"
    assert not (lib / "山风" / "cards" / "斩.yaml").exists()
    assert load_card(lib, "山风", "斩改")["name"] == "斩改"


def test_rename_card_with_id_keeps_stem(lib):
    """有 id 卡改名：文件名与卡名脱钩保持不动（BWPro 按 id 取文件）。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "100301", {**FIGHT, "id": "100301"})
    path, _ = save_card(lib, "山风", "100301", {**FIGHT, "id": "100301", "name": "斩改"})
    assert path.name == "100301.yaml"
    assert load_card(lib, "山风", "100301")["name"] == "斩改"


def test_rename_card_custom_stem_kept(lib):
    """文件名本就和卡名脱钩（数字 stem 无 id）：改名不重命名。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "100301", FIGHT)  # stem 100301 ≠ 卡名 斩
    path, _ = save_card(lib, "山风", "100301", {**FIGHT, "name": "斩改"})
    assert path.name == "100301.yaml"


def test_rename_card_file_conflict(lib):
    """无 id 改名的目标文件名已存在：报 SchemaError，原文件不动。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "斩", FIGHT)
    save_card(lib, "山风", "突", {**FIGHT, "name": "突"})
    with pytest.raises(SchemaError, match="已存在"):
        save_card(lib, "山风", "斩", {**FIGHT, "name": "突"})
    assert load_card(lib, "山风", "斩")["name"] == "斩"


def test_rename_card_illegal_name(lib):
    """无 id 改名但新卡名不是合法文件名：报 SchemaError 并指引填写 id，不落盘。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "斩", FIGHT)
    with pytest.raises(SchemaError, match="id"):
        save_card(lib, "山风", "斩", {**FIGHT, "name": "斩:改"})
    assert load_card(lib, "山风", "斩")["name"] == "斩"  # 原文件内容不变


def test_rename_conflict_keeps_references_intact(lib):
    """式神改名但重命名目标冲突：报错时引用联动不得先行落盘（悬空引用回归）。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "山风", SHIKIGAMI)                      # 文件按卡名回退命名
    save_card(lib, "山风", "岚", {**SHIKIGAMI, "name": "薰"})      # 占用目标文件名（卡名不同）
    save_card(lib, "山风", "斩", FIGHT)                            # shikigami: 山风
    with pytest.raises(SchemaError, match="已存在"):
        save_card(lib, "山风", "山风", {**SHIKIGAMI, "name": "岚"})
    assert load_card(lib, "山风", "斩")["shikigami"] == "山风"      # 引用未被先行改写
    assert load_card(lib, "山风", "山风")["name"] == "山风"         # 原卡未落盘
    # 换一个不冲突的名字重试：联动正常生效
    _, updated = save_card(lib, "山风", "山风", {**SHIKIGAMI, "name": "山风改"})
    assert updated == ["斩"]
    assert load_card(lib, "山风", "斩")["shikigami"] == "山风改"


def test_rename_card_case_only(lib):
    """纯大小写改名（Windows 大小写不敏感）不误判自身为冲突。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "zhan", {**FIGHT, "name": "zhan"})
    path, _ = save_card(lib, "山风", "zhan", {**FIGHT, "name": "Zhan"})
    assert load_card(lib, "山风", path.stem)["name"] == "Zhan"


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
    {**SHIKIGAMI, "level": 2},                          # 标记扩展：式神可选等级
    {**SHIKIGAMI, "faction_style": 1},                  # 标记扩展：派系样式 1-3
    {**SHIKIGAMI, "level_color": "cyan"},               # 勾玉颜色（凡可带 level 者皆可）
    {**FIGHT, "level_color": "brown"},
    {**ASSIST, "level_color": "purple"},
    {**ASSIST, "duo_frame": True},                      # 协战双式神框开关（可选布尔）
    {**SHIKIGAMI, "portrait": {}},                      # 头像变换段：全键可缺省
    {**SHIKIGAMI, "portrait": {"offset_x": 4, "offset_y": -2, "scale": 1.2, "rotate": 15}},
    {**SHIKIGAMI, "portrait": {"frame": False}},        # 头像框开关（可选布尔）
    {**SHIKIGAMI, "power_color": "red"},                # 数值变色（红=debuff/受伤）
    {**FIGHT, "shield+_color": "green"},                # 绿=buff
    {**FIELD, "durability_color": "purple"},            # 紫=中毒
    FORM,
    FIELD,
    ASSIST,
    {**FIGHT, "artwork": {"images": [
        {"path": "a.png"},
        {"path": "b.png", "offset_x": 0, "offset_y": -12, "scale": 1.15, "rotate": 30},
        {},
    ]}},
    {"type": "法术", "name": "最简", "rarity": "N"},
    {"type": "法术", "name": "带 id", "id": "100301", "rarity": "N"},
    {"type": "法术", "name": "衍生"},                  # rarity/level 均可缺省（衍生牌口径）
    {"type": "战斗", "name": "衍生斩", "power+": -1},   # 缺稀有度+带符号数值
    {**FIGHT, "layout": {"elements": {"name": {"pos": [1, 2]}},
                         "text_regions": {"desc": {"width": 300}}}},  # 单卡布局覆盖段
])
def test_validate_ok(card):
    assert validate_card(card) == []


# ---------- schema 校验：反例（消息含字段名） ----------

@pytest.mark.parametrize("card, needle", [
    ({"name": "x"}, "type"),
    ({**FIGHT, "type": "装备"}, "type"),
    ({**FIGHT, "name": ""}, "name"),
    ({**FIGHT, "id": 100301}, "id"),
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
    ({**ASSIST, "duo_frame": "是"}, "duo_frame"),       # 必须布尔
    ({**FIGHT, "duo_frame": True}, "duo_frame"),        # 双式神框为协战专属（白名单之外）
    ({**FIGHT, "portrait": {}}, "portrait"),            # 头像变换段为式神专属（白名单之外）
    ({**SHIKIGAMI, "portrait": []}, "portrait"),        # 必须是映射
    ({**SHIKIGAMI, "portrait": {"scale": 0}}, "portrait"),        # scale 须正数
    ({**SHIKIGAMI, "portrait": {"offset_x": "1"}}, "portrait"),   # 数值键须数字
    ({**SHIKIGAMI, "portrait": {"zoom": 1}}, "portrait"),         # 未知键
    ({**SHIKIGAMI, "portrait": {"frame": "否"}}, "portrait"),     # frame 必须布尔
    ({**SHIKIGAMI, "power": True}, "power"),          # bool 不算 int
    ({**SHIKIGAMI, "health": -1}, "health"),          # 非负
    ({**FIGHT, "power+": "1"}, "power+"),
    # 表外组合（stat 适用矩阵）
    ({**FIGHT, "power": 1}, "power"),                 # 战斗无裸 power
    ({**SPELL, "power+": 1}, "power+"),               # 非觉醒法术无 stat
    ({**FORM, "durability": 3}, "durability"),
    ({**FIELD, "health": 3}, "health"),
    ({**ASSIST, "power+": 1}, "power+"),
    ({**SHIKIGAMI, "level": 4}, "level"),             # 式神等级同样限 1-3
    ({**SHIKIGAMI, "level": "1"}, "level"),
    ({**SHIKIGAMI, "faction_style": 4}, "faction_style"),
    ({**SHIKIGAMI, "faction_style": "2"}, "faction_style"),
    ({**FIGHT, "faction_style": 1}, "faction_style"),   # 派系样式为式神专属（白名单之外）
    ({**FIGHT, "level_color": "gold"}, "level_color"),  # 非法勾玉颜色
    ({**FIGHT, "power+_color": "blue"}, "power+_color"),  # 数值变色仅 red/green/purple
    ({**FIGHT, "health_color": "red"}, "health_color"),   # 变色伴随字段须在 stat 矩阵内
    ({**SHIKIGAMI, "rarity": "R"}, "rarity"),         # 式神无稀有度
    ({**FIGHT, "未知字段": 1}, "未知字段"),
    ({**FIGHT, "layout": "x"}, "layout"),                        # 布局覆盖段须为映射
    ({**FIGHT, "layout": {"junk": {}}}, "layout.junk"),          # 只允许 elements/text_regions
    ({**FIGHT, "layout": {"elements": {"name": "x"}}}, "layout.elements"),  # 项须为键值映射
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


# ---------- 机制（全局共享池 library/mechanisms/） ----------

MECH = {"name": "蛊蚀", "frame": "skill", "text": "敌方式神气绝时结附。"}
MECH_SEAL = {"name": "加护", "frame": "seal", "text": "恢复2点生命。", "badge": "bless"}


def test_mechanism_round_trip(lib):
    path = save_mechanism(lib, "蛊蚀", MECH)
    assert path == lib / "mechanisms" / "蛊蚀.yaml"
    assert load_mechanism(lib, "蛊蚀") == with_today(MECH)
    assert list_mechanisms(lib) == [entry("蛊蚀", "蛊蚀")]


def test_mechanisms_global_not_project(lib):
    """机制是全局共享池：不占项目列表，list_projects 不返回 mechanisms 目录。"""
    create_project(lib, "山风")
    save_mechanism(lib, "蛊蚀", MECH)
    assert list_projects(lib) == ["山风"]
    with pytest.raises(StoreError, match="保留"):
        create_project(lib, "mechanisms")
    with pytest.raises(StoreError, match="保留"):
        rename_project(lib, "山风", "mechanisms")


def test_mechanism_rename_renames_file(lib):
    save_mechanism(lib, "蛊蚀", MECH)
    path = save_mechanism(lib, "蛊蚀", {**MECH, "name": "魔蛊"})
    assert path.stem == "魔蛊"
    assert not (lib / "mechanisms" / "蛊蚀.yaml").exists()
    assert load_mechanism(lib, "魔蛊")["name"] == "魔蛊"
    assert list_mechanisms(lib) == [entry("魔蛊", "魔蛊")]


def test_mechanism_rename_conflict(lib):
    save_mechanism(lib, "蛊蚀", MECH)
    save_mechanism(lib, "加护", MECH_SEAL)
    with pytest.raises(SchemaError, match="已存在"):
        save_mechanism(lib, "蛊蚀", {**MECH, "name": "加护"})
    # 冲突报错后原文件保持不动
    assert load_mechanism(lib, "蛊蚀")["name"] == "蛊蚀"
    assert load_mechanism(lib, "加护")["name"] == "加护"


def test_mechanism_delete(lib):
    save_mechanism(lib, "蛊蚀", MECH)
    delete_mechanism(lib, "蛊蚀")
    assert list_mechanisms(lib) == []
    with pytest.raises(StoreError) as e:
        delete_mechanism(lib, "蛊蚀")
    assert e.value.code == "not_found"


def test_mechanism_load_not_found(lib):
    with pytest.raises(StoreError) as e:
        load_mechanism(lib, "不存在")
    assert e.value.code == "not_found"


def test_mechanism_name_injection_rejected(lib):
    with pytest.raises(StoreError) as e:
        save_mechanism(lib, "../evil", {**MECH, "name": "x"})
    assert e.value.code == "invalid_name"


def test_mechanism_save_validates_schema(lib):
    with pytest.raises(SchemaError, match="frame"):
        save_mechanism(lib, "蛊蚀", {**MECH, "frame": "gold"})
    assert list_mechanisms(lib) == []  # 校验不过不落盘


@pytest.mark.parametrize("mech", [
    MECH,
    MECH_SEAL,
    {"name": "最简", "frame": "skill"},  # text/badge 全可缺省
    {**MECH, "badge": None},             # badge 可显式留空
    {**MECH, "chars_per_line": 12},
])
def test_validate_mechanism_ok(mech):
    assert validate_mechanism(mech) == []


@pytest.mark.parametrize("mech, needle", [
    (["不是映射"], "映射"),
    ({"frame": "skill"}, "name"),                       # 缺关键字名
    ({**MECH, "name": "  "}, "name"),
    ({"name": "x"}, "frame"),                           # 缺框类型
    ({**MECH, "frame": "gold"}, "frame"),               # 非法框类型
    ({**MECH, "text": 1}, "text"),                      # 描述必须是字符串
    ({**MECH, "marks": ["unique"]}, "marks"),           # marks 已移除：白名单之外
    ({**MECH_SEAL, "badge": "gold"}, "badge"),          # 非法圆形角标
    ({**MECH, "badge": "bless"}, "badge"),              # badge 仅 seal 框可携带
    ({**MECH, "chars_per_line": 0}, "chars_per_line"),
    ({**MECH, "chars_per_line": -1}, "chars_per_line"),
    ({**MECH, "chars_per_line": 1.5}, "chars_per_line"),
    ({**MECH, "chars_per_line": True}, "chars_per_line"),
    ({**MECH, "未知字段": 1}, "未知字段"),
])
def test_validate_mechanism_rejects(mech, needle):
    errors = validate_mechanism(mech)
    assert errors, f"应判非法：{mech}"
    assert any(needle in e for e in errors), errors


def test_mechanism_load_migrates_legacy_marks(lib):
    """旧机制文件里的 marks 键（唯一/瞬发角标，已移除）读取时静默丢弃，保存不写回。"""
    import yaml
    mdir = lib / "mechanisms"
    mdir.mkdir(parents=True)
    (mdir / "旧机制.yaml").write_text(
        yaml.safe_dump({**MECH, "name": "旧机制", "marks": ["unique"]},
                       allow_unicode=True), encoding="utf-8")
    data = load_mechanism(lib, "旧机制")
    assert "marks" not in data


# ---------- 版本日期与多版本（v1.6.0） ----------

from bwpdiy.store import (
    cleanup_unused_images,
    new_card_version,
    new_mechanism_version,
)


def test_version_date_schema(lib):
    assert validate_card({**FIGHT, "version_date": "20261025"}) == []
    assert validate_card({**FIGHT, "version_date": ""}) == []  # 空串=未填，保存时填当天
    assert "version_date" in str(validate_card({**FIGHT, "version_date": "20261301"}))
    assert "version_date" in str(validate_card({**FIGHT, "version_date": "20260230"}))
    assert "version_date" in str(validate_card({**FIGHT, "version_date": "2026/10/25"}))
    assert "version_date" in str(validate_card({**FIGHT, "version_date": 20261025}))
    assert validate_mechanism({**MECH, "version_date": "20261025"}) == []
    assert "version_date" in str(validate_mechanism({**MECH, "version_date": "昨天"}))


def test_list_cards_groups_by_id_and_name(lib):
    """id+name 均相同才归组；条目 stem=最新版本，count=版本数，versions 降序。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "10030701", {**FIGHT, "id": "10030701", "version_date": "20260101"})
    save_card(lib, "山风", "10030701@20260201",
              {**FIGHT, "id": "10030701", "version_date": "20260201"})
    save_card(lib, "山风", "20030701", {**FIGHT, "id": "20030701"})  # 同名不同 id：不合并
    listed = list_cards(lib, "山风")["cards"]
    assert len(listed) == 2
    group = next(c for c in listed if c["id"] == "10030701")
    assert group["stem"] == "10030701@20260201" and group["count"] == 2
    assert [v["stem"] for v in group["versions"]] == ["10030701@20260201", "10030701"]
    assert [v["date"] for v in group["versions"]] == ["20260201", "20260101"]


def test_list_cards_versions_carry_deck_snapshot_metadata(lib):
    """历史卡组校验需要逐版本的稀有度和所属式神，不能只看最新版本。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "斩", {**FIGHT, "version_date": "20260101"})
    save_card(lib, "山风", "斩@20260201",
              {**FIGHT, "rarity": "SR", "shikigami": "薰", "version_date": "20260201"})
    versions = list_cards(lib, "山风")["cards"][0]["versions"]
    assert versions[0] == {"stem": "斩@20260201", "date": "20260201", "type": "战斗",
                           "rarity": "SR", "shikigami": "薰",
                           "shikigami1": None, "shikigami2": None}
    assert versions[1] == {"stem": "斩", "date": "20260101", "type": "战斗", "rarity": "R",
                           "shikigami": "山风", "shikigami1": None, "shikigami2": None}


def test_save_propagates_shared_layout_and_artwork(lib):
    """同组共享 layout/artwork：保存任一版本同步到其他版本；键删除同样同步。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "斩", FIGHT)
    save_card(lib, "山风", "斩@20260102", {**FIGHT, "version_date": "20260102"})
    v2 = {**FIGHT, "version_date": "20260102",
          "layout": {"elements": {"name": {"pos": [1, 2]}}},
          "artwork": {"images": [{"path": "a.png", "offset_x": 5}]}}
    save_card(lib, "山风", "斩@20260102", v2)
    old = load_card(lib, "山风", "斩")
    assert old["layout"] == v2["layout"] and old["artwork"] == v2["artwork"]
    # 老版本再保存（无 layout/artwork）：同步删除新版本的这两段
    save_card(lib, "山风", "斩", FIGHT)
    new = load_card(lib, "山风", "斩@20260102")
    assert "layout" not in new and "artwork" not in new


def test_card_limit_counts_groups(lib, monkeypatch):
    """数量限制按组计：同组新版本不重复占名额。"""
    import bwpdiy.store.projects as projects
    monkeypatch.setattr(projects, "MAX_CARDS", 1)
    create_project(lib, "山风")
    save_card(lib, "山风", "斩", FIGHT)
    with pytest.raises(StoreError, match="上限"):
        save_card(lib, "山风", "烈", SPELL)
    path = new_card_version(lib, "山风", "斩", "20260102")
    assert path.name == "斩@20260102.yaml"  # 同组新版本不受组数限制


def test_version_date_change_renames_at_stem(lib):
    """带 @ 文件改日期→重命名；无 @ 旧文件不因日期改名；目标冲突拒绝。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "斩@20260101", {**FIGHT, "version_date": "20260101"})
    path, _ = save_card(lib, "山风", "斩@20260101", {**FIGHT, "version_date": "20260301"})
    assert path.name == "斩@20260301.yaml"
    assert not (lib / "山风" / "cards" / "斩@20260101.yaml").exists()
    save_card(lib, "山风", "烈", SPELL)
    path, _ = save_card(lib, "山风", "烈", {**SPELL, "version_date": "20260401"})
    assert path.name == "烈.yaml"  # 无 @ 不迁移命名
    save_card(lib, "山风", "斩@20260501", {**FIGHT, "version_date": "20260501"})
    with pytest.raises(SchemaError, match="已存在"):
        save_card(lib, "山风", "斩@20260501", {**FIGHT, "version_date": "20260301"})


def test_new_card_version_copies_latest(lib):
    create_project(lib, "山风")
    save_card(lib, "山风", "斩", {**FIGHT, "version_date": "20260101", "power+": 1})
    save_card(lib, "山风", "斩@20260201", {**FIGHT, "version_date": "20260201", "power+": 9})
    path = new_card_version(lib, "山风", "斩", "20260301")  # 传入旧版 stem 也复制最新版
    data = load_card(lib, "山风", path.stem)
    assert data["power+"] == 9 and data["version_date"] == "20260301"
    with pytest.raises(StoreError, match="已存在"):
        new_card_version(lib, "山风", "斩", "20260301")
    path = new_card_version(lib, "山风", "斩", "")  # 留空取当天
    assert path.stem.endswith(f"@{TODAY}")


def test_mechanism_versions(lib):
    save_mechanism(lib, "蛊蚀", {**MECH, "version_date": "20260101"})
    path = new_mechanism_version(lib, "蛊蚀", "20260201")
    assert path.name == "蛊蚀@20260201.yaml"
    listed = list_mechanisms(lib)
    assert len(listed) == 1 and listed[0]["count"] == 2
    assert listed[0]["stem"] == "蛊蚀@20260201"
    # 带 @ 文件改日期重命名；改机制名同理
    path = save_mechanism(lib, "蛊蚀@20260201",
                          {**MECH, "version_date": "20260301"})
    assert path.name == "蛊蚀@20260301.yaml"
    path = save_mechanism(lib, "蛊蚀@20260301",
                          {**MECH, "name": "魔蛊", "version_date": "20260301"})
    assert path.name == "魔蛊@20260301.yaml"
    with pytest.raises(StoreError, match="已存在"):
        new_mechanism_version(lib, "魔蛊@20260301", "20260301")


def test_blank_mechanism_date_is_saved_as_compact_yyyymmdd(lib):
    path = save_mechanism(lib, "蛊蚀", {**MECH, "version_date": ""})
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert raw["version_date"] == TODAY and "-" not in raw["version_date"]


def test_new_mechanism_version_rejects_missing_name(lib):
    mdir = lib / "mechanisms"
    mdir.mkdir(parents=True)
    (mdir / "坏.yaml").write_text("frame: skill\ntext: ''\n", encoding="utf-8")
    with pytest.raises(StoreError, match="缺少有效名称"):
        new_mechanism_version(lib, "坏", "20260101")


def test_cleanup_unused_images(lib):
    create_project(lib, "山风")
    images = lib / "山风" / "images"
    save_card(lib, "山风", "斩", {**FIGHT, "artwork": {"images": [{"path": "used.png"}]}})
    save_card(lib, "山风", "烈", SPELL)  # 无 artwork：缺省引用 烈.png
    for name in ("used.png", "烈.png", "orphan.png", "orphan.jpg"):
        (images / name).write_bytes(b"x")
    (images / "notes.txt").write_text("keep", encoding="utf-8")
    deleted = cleanup_unused_images(lib)
    assert sorted(d.replace("\\", "/") for d in deleted) == ["山风/images/orphan.jpg", "山风/images/orphan.png"]
    assert (images / "used.png").is_file() and (images / "烈.png").is_file()
    assert (images / "notes.txt").is_file()  # 非图片不动


def test_cleanup_preserves_all_images_when_any_yaml_is_broken(lib):
    """损坏 YAML 不可按“无引用”处理：整个项目跳过清理，避免二次数据损失。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "斩", {**FIGHT, "artwork": {"images": [{"path": "used.png"}]}})
    images = lib / "山风" / "images"
    (images / "used.png").write_bytes(b"used")
    (images / "orphan.png").write_bytes(b"orphan")
    (lib / "山风" / "cards" / "斩.yaml").write_text("name: [unterminated", encoding="utf-8")
    assert cleanup_unused_images(lib) == []
    assert (images / "used.png").is_file() and (images / "orphan.png").is_file()


def test_cleanup_normalizes_relative_artwork_paths(lib):
    """sub/../used.png 与 used.png 是同一引用，路径未归一不得误删。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "斩", {**FIGHT, "artwork": {"images": [{"path": "sub/../used.png"}]}})
    images = lib / "山风" / "images"
    (images / "used.png").write_bytes(b"used")
    (images / "orphan.png").write_bytes(b"orphan")
    deleted = cleanup_unused_images(lib)
    assert [Path(d).name for d in deleted] == ["orphan.png"]
    assert (images / "used.png").is_file()


def test_shikigami_rename_failure_rolls_back_references(lib, monkeypatch):
    """主卡写盘失败时，已改写的引用也必须回滚，不能留下悬空新名。"""
    from bwpdiy.store import projects
    create_project(lib, "山风")
    save_card(lib, "山风", "旧名", {**SHIKIGAMI, "name": "旧名"})
    save_card(lib, "山风", "斩", {**FIGHT, "shikigami": "旧名"})
    original = projects._dump_yaml

    def fail_main(path, data):
        if path.name == "旧名.yaml" and data.get("name") == "新名":
            raise OSError("模拟主文件写盘失败")
        return original(path, data)

    monkeypatch.setattr(projects, "_dump_yaml", fail_main)
    with pytest.raises(OSError, match="模拟主文件"):
        save_card(lib, "山风", "旧名", {**SHIKIGAMI, "name": "新名"})
    assert load_card(lib, "山风", "旧名")["name"] == "旧名"
    assert load_card(lib, "山风", "斩")["shikigami"] == "旧名"


def test_list_cards_treats_malformed_group_key_as_broken_entry(lib):
    """手改 name 为列表时仅该文件标损坏，不得让 unhashable 值拖垮项目列表。"""
    create_project(lib, "山风")
    (lib / "山风" / "cards" / "bad.yaml").write_text("name: [坏, 列表]\ntype: 战斗\n", encoding="utf-8")
    listed = list_cards(lib, "山风")["cards"]
    assert len(listed) == 1 and listed[0]["stem"] == "bad" and listed[0]["name"] is None


def test_schema_rejects_nonfinite_layout_values_and_overlong_stats(lib):
    """NaN/Infinity 与超 12 位数值在保存前拒绝，避免异常渲染/巨量分配。"""
    base = {**SHIKIGAMI, "artwork": {"images": [{"scale": float("nan")}]}}
    assert any("scale" in e for e in validate_card(base))
    assert any("offset_x" in e for e in validate_card(
        {**SHIKIGAMI, "portrait": {"offset_x": float("inf")}}))
    assert any("layout" in e for e in validate_card(
        {**SHIKIGAMI, "layout": {"elements": {"name": {"pos": [float("inf"), 0]}}}}))
    assert any("12 位" in e for e in validate_card({**SHIKIGAMI, "power": 10 ** 12}))


def test_legacy_dashed_version_date_normalized(lib):
    """旧带短横线日期（v1.6.0）：保存/读取归一为 8 位数字（v1.6.1）。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "斩", {**FIGHT, "version_date": "2026-01-02"})
    assert load_card(lib, "山风", "斩")["version_date"] == "20260102"
    save_mechanism(lib, "蛊蚀", {**MECH, "version_date": "2026-01-02"})
    assert load_mechanism(lib, "蛊蚀")["version_date"] == "20260102"


def test_shorthand_id_expands_with_shikigami(lib):
    """两位 id 简写（v1.6.2）：有所属式神且其 id 为 6 位时保存展开为全长。"""
    create_project(lib, "山风")
    save_card(lib, "山风", "100307", {**SHIKIGAMI, "id": "100307"})
    save_card(lib, "山风", "斩", {**FIGHT, "id": "01"})
    assert load_card(lib, "山风", "斩")["id"] == "10030701"
    save_card(lib, "山风", "共鸣", {**ASSIST, "id": "02"})  # 协战双式神前缀歧义：不展开
    assert load_card(lib, "山风", "共鸣")["id"] == "02"
    save_card(lib, "山风", "中立", {**FIGHT, "name": "中立", "shikigami": "", "id": "03"})
    assert load_card(lib, "山风", "中立")["id"] == "03"  # 无所属式神：不展开
    save_card(lib, "山风", "200307", {**SHIKIGAMI, "name": "薰", "id": "abc"})
    save_card(lib, "山风", "烈", {**SPELL, "shikigami": "薰", "id": "04"})
    assert load_card(lib, "山风", "烈")["id"] == "04"  # 式神 id 非 6 位：不展开
    save_card(lib, "山风", "斩", {**FIGHT, "id": "10030701"})  # 全长：原样
    assert load_card(lib, "山风", "斩")["id"] == "10030701"
