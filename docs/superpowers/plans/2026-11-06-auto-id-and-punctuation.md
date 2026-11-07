# 自动编号与描述标点避让实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为项目和卡牌提供统一、无冲突的自动 ID，并让自动换行避免把闭合标点留在行首。

**Architecture:** `store/projects.py` 负责项目元数据、全库占用扫描和编号分配，保存与上传都经 store 落盘；Web 层只传递当前表单并返回最终 ID。`render/text.py` 在贪心换行时携带前一项与连续标点，复用现有适配管线，不新增依赖。

**Tech Stack:** Python 3.12、Pillow、PyYAML、FastAPI、原生 JavaScript、pytest。

## Global Constraints

- 设计依据：`docs/superpowers/specs/2026-11-06-auto-id-and-punctuation-design.md`；衍生卡与衍生物式神共用 `51–99`，分别从两端取空号，无固定分界。
- 中立牌从 `19999999` 起全库递减；BWPro 同步另批处理，本计划不修改 BWPro。
- schema 字段只增不改；render 不得 import store/web；不新增依赖，不改变前端经典脚本顺序。
- 项目 ID 全库唯一，修改只影响之后的自动编号；完整卡牌 ID 生成时也跳过全库占用。
- 自动补 ID 必须同步同一 `id+name` 旧空白 ID 版本组，不能把历史版本拆成不同卡组。
- 测试命令：`PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q`；提交使用中文 conventional 格式，每次提交后 `git push`。

---

### Task 1: 项目元数据与 store 自动编号

**Files:**
- Modify: `bwpdiy/store/projects.py`
- Modify: `bwpdiy/store/schema.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Produces: `create_project(library: Path, project: str, project_id: str = "") -> Path`
- Produces: `load_project(library: Path, project: str) -> dict`，返回 `{"id": str}`。
- Produces: `save_project_id(library: Path, project: str, project_id) -> str`。
- Produces: `ensure_card_id(library: Path, project: str, data: dict) -> str`，原地写入并返回 `data["id"]`。
- Consumes: 现有 `_read_yaml`、`_dump_yaml`、`_card_group`、`_group_key`、`save_card` 与 `StoreError`。

- [ ] **Step 1: 写项目元数据与 token schema 的失败测试**

在 `tests/test_store.py` 增加：

```python
def test_project_id_round_trip_and_unique(lib):
    create_project(lib, "甲", "051")
    create_project(lib, "乙")
    assert load_project(lib, "甲") == {"id": "051"}
    assert load_project(lib, "乙") == {"id": ""}
    with pytest.raises(StoreError, match="三位"):
        save_project_id(lib, "乙", "51")
    with pytest.raises(StoreError, match="已使用"):
        save_project_id(lib, "乙", "051")
    assert save_project_id(lib, "乙", "052") == "052"


def test_token_schema_is_explicit_and_type_scoped():
    assert validate_card({**FIGHT, "token": True}) == []
    assert any("白名单" in e for e in validate_card({**SHIKIGAMI, "token": True}))
    assert any("token" in e for e in validate_card({**FIGHT, "token": 1}))
```

- [ ] **Step 2: 运行新测试并确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_store.py -q`
Expected: 因项目元数据函数和 `token` 白名单尚不存在而 FAIL。

- [ ] **Step 3: 实现项目 ID 元数据与校验**

项目根目录使用 `project.yaml`；读取空/缺失文件时返回 `{"id": ""}`，非映射或非法 ID 报 `StoreError(code="invalid_data")`。手动值只接受 `str` 且完整匹配 `^\d{3}$`，唯一性冲突用 `already_exists`。创建空项目时空白 ID 可不写文件，非空 ID 用 `_dump_yaml` 写入。

核心校验形状：

```python
def _project_id_in_use(library: Path, project_id: str, exclude: str) -> bool:
    return any(p != exclude and load_project(library, p)["id"] == project_id
               for p in list_projects(library))
```

- [ ] **Step 4: 写各号段、空号、协战与多版本的失败测试**

至少覆盖以下精确结果：

```python
def test_auto_id_ranges_and_gap_reuse(lib):
    create_project(lib, "项目")
    save_card(lib, "项目", "甲", {**SHIKIGAMI, "name": "甲"})
    save_card(lib, "项目", "乙", {**SHIKIGAMI, "name": "乙"})
    assert load_card(lib, "项目", "甲")["id"] == "05101"
    assert load_card(lib, "项目", "乙")["id"] == "05102"
    save_card(lib, "项目", "斩", {**FIGHT, "shikigami": "甲"})
    save_card(lib, "项目", "衍生", {**FIGHT, "name": "衍生", "shikigami": "甲", "token": True})
    summon = {**SHIKIGAMI, "name": "召唤", "shikigami": "甲"}
    save_card(lib, "项目", "召唤", summon)
    assert load_card(lib, "项目", "斩")["id"] == "0510101"
    assert load_card(lib, "项目", "衍生")["id"] == "0510151"
    assert load_card(lib, "项目", "召唤")["id"] == "0510199"


def test_auto_id_neutral_and_shared_derivative_range(lib):
    create_project(lib, "项目", "051")
    save_card(lib, "项目", "中立", {**FIGHT, "name": "中立", "shikigami": ""})
    assert load_card(lib, "项目", "中立")["id"] == "19999999"
    # 分别在 51 与 99 已占用时，下一张衍生卡取 52、下一只衍生物取 98。
```

协战测试须让两位所属式神 ID 为 `05102`/`05101`，断言首张协战为 `0510121`。另建 `05103` 后删除 `05102` 的空文件场景可用 `delete_card`，断言下一主要式神补 `05102`。

多版本测试先手工建立同一空白 ID + 同名的 `@20260101`、`@20260201` 两文件，再保存其中一个，断言两个 YAML 都写入相同自动 ID，且 `list_cards` 仍只有一组。

- [ ] **Step 5: 实现统一编号分配**

增加内部扫描函数，安全忽略损坏 YAML，但收集所有字符串 ID：

```python
def _all_card_data(library: Path) -> list[dict]:
    records = []
    for project_name in list_projects(library):
        pdir = library / project_name
        for sub in ("shikigami", "cards"):
            cdir = pdir / sub
            for path in sorted(cdir.glob("*.yaml")) if cdir.is_dir() else []:
                data = _read_yaml(path)
                if data:
                    records.append(data)
    return records
```

分配器接收有序候选完整 ID，返回第一个不在 `used_ids` 的值；无候选则抛 `StoreError("该类别自动 ID 号段已耗尽", code="forbidden")`。规则：

- 主要式神：先确保项目 ID（`051..999` 最小空号），候选 `<pid>{seq:02d}`，`seq=1..99`。
- 普通所属卡：确保 `shikigami` 指向的主要式神有 ID，候选前缀 + `01..20`。
- 协战：确保两位所属式神均有六位数字 ID，以数值较小者为前缀，候选 `21..50`。
- `token is True` 的有所属非协战卡：候选前缀 + `51..99`。
- 有 `shikigami` 的式神：候选前缀 + `99..51`。
- 无所属非式神卡：候选 `19999999..10000000`。
- 已有非空 ID 直接返回；所属引用不存在或所属 ID 不是六位数字时给出明确 `invalid_data`，不得自行覆盖手动非法 ID。

主要式神依赖补号可找到其最新 stem 后递归调用 `save_card`；递归到主要式神后终止。所有分配都扫描全库完整 ID，而非仅当前项目。

- [ ] **Step 6: 接入 save_card 并保持版本归组**

在首次 schema 校验后调用 `ensure_card_id`。读取旧文件后，如果旧数据 ID 空白而新数据有 ID，记录旧 `_group_key(old)`；事务的 `affected` 纳入该旧组全部文件，主文件写盘后把同旧组其他版本的 `id` 同步为新 ID。该同步与现有备份/回滚共用事务。

同时保留手动给旧空白 ID 卡补号时的版本归组，不限于自动分配路径。

- [ ] **Step 7: 运行 store 测试并提交**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_store.py -q`
Expected: PASS。

```bash
git add bwpdiy/store/projects.py bwpdiy/store/schema.py tests/test_store.py
git commit -m "feat(卡牌库): 自动分配项目与卡牌编号"
git push
```

### Task 2: Web API 与编辑器自动编号接线

**Files:**
- Modify: `bwpdiy/web/app.py`
- Modify: `bwpdiy/web/static/editor-cards.js`
- Modify: `bwpdiy/web/static/editor-main.js`（仅在总未保存检查位于此文件时接入项目脏标记）
- Test: `tests/test_web_projects.py`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: Task 1 的 `create_project`、`load_project`、`save_project_id`。
- Produces: `GET /api/projects/{name}/meta -> {"id": str}`。
- Produces: `PUT /api/projects/{name}/meta`，body `{"id": str}`，返回 `{"ok": true, "id": str}`。
- Changes: `POST /api/projects` 接受 `{"name": str, "id": str?}`。
- Changes: 卡牌保存与上传响应增加 `"id": str`；上传查询参数增加 `token/shikigami/shikigami1/shikigami2`，用于当前表单的编号分类。

- [ ] **Step 1: 写项目 API、保存响应与上传编号的失败测试**

在 `tests/test_web_projects.py` 增加：

```python
def test_project_metadata_api(client):
    assert client.post("/api/projects", json={"name": "项目", "id": "051"}).status_code == 200
    assert client.get("/api/projects/项目/meta").json() == {"id": "051"}
    r = client.put("/api/projects/项目/meta", json={"id": "052"})
    assert r.status_code == 200 and r.json()["id"] == "052"
    assert client.put("/api/projects/项目/meta", json={"id": "52"}).status_code == 422


def test_save_returns_assigned_id(client):
    client.post("/api/projects", json={"name": "项目"})
    r = client.put("/api/projects/项目/cards/甲", json=_shikigami_card("甲"))
    assert r.status_code == 200 and r.json()["id"] == "05101"


def test_upload_uses_current_token_and_returns_id(client, library_dir):
    client.post("/api/projects", json={"name": "项目", "id": "051"})
    client.put("/api/projects/项目/cards/甲", json=_shikigami_card("甲"))
    client.put("/api/projects/项目/cards/衍生", json=_battle_card("衍生"))
    r = client.post("/api/projects/项目/cards/衍生/artwork?filename=a.png&token=1&shikigami=测试式神",
                    content=SAMPLE_ART.read_bytes())
    assert r.status_code == 200
    assert r.json()["id"] == "0510151"
```

测试中的图片字节复用该文件现有合法 PNG 构造方式，不引入固定无效 payload。上传后再GET，断言 `id`、图片路径和 `token` 与当前表单一致。

- [ ] **Step 2: 运行测试并确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_web_projects.py -q`
Expected: 新路由/响应字段不存在而 FAIL。

- [ ] **Step 3: 实现 Web 路由与响应**

导入 Task 1 新函数。项目 PUT 继续只处理 `new_name`；元数据走独立 `/meta`，避免混淆目录重命名与 ID 保存。

保存：

```python
path, updated = save_card(library_dir, project, card, request)
saved = load_card(library_dir, project, path.stem)
return {"ok": True, "updated": updated, "stem": path.stem, "id": saved["id"]}
```

上传在现有图片校验后、文件名计算前，对查询参数中实际出现的编号字段覆盖 `card_data`；`token=1` 写 `True`，`token=0` 删除/写 `False`，其他值 422。所属字段允许空串以识别中立牌。先调用 `ensure_card_id` 原地补号，再计算文件名，最终由 `save_card` 落盘并同步版本组：

```python
ensure_card_id(library_dir, project, card_data)
filename = f"{card_data['id']}{ext}"
path, _ = save_card(library_dir, project, card, card_data)
return {"ok": True, "path": filename, "id": card_data["id"]}
```

实际代码保留现有冲突后缀、原子图片写入和异常回滚，上面仅展示编号、文件名与响应的赋值顺序。

- [ ] **Step 4: 实现项目编辑界面**

`selectProject` 在确认未保存修改后清空卡牌/机制选择并加载项目元数据；调用 `loadCards(..., select_first=False)`，不再自动选第一张卡。其他现有加载/新建流程默认仍自动选卡。

`buildForm` 在无 `formData` 但有 `curProject` 时显示：

```javascript
textRow(div, '项目 ID（3位，留空自动分配）', projectData.id ?? '', v => {
  projectData.id = v; pDirty = true;
  cStatusEl.textContent = '项目 ID 未保存';
});
```

增加“保存项目 ID”按钮调用 `/meta`。`pDirty` 纳入切换项目/卡牌/机制、关闭标签页及退出工具的统一未保存检查；保存成功清除。新建项目使用现有通用输入区的名称 + 可留空项目 ID 两字段，预留 `mechanisms` 校验不变。

- [ ] **Step 5: 接入衍生牌勾选和最终 ID 回写**

非式神、非协战卡在右栏显示“衍生牌”：

```javascript
checkRowC(div, '衍生牌', !!formData.token, v => {
  if (v) formData.token = true; else delete formData.token;
  afterEdit(true);
});
```

前端 `validateCardJS` 的类型白名单加入同范围 `token` 并校验布尔值。`confirmFallbackNaming` 删除 ID 回退提示，仅保留版本日期提示。

保存成功后在构造 `cardData` 前执行 `payload.id = res.id`，再按现有 revision 规则同步；上传查询附上当前 `token` 与所属字段，成功后同步 `formData.id`、`cardData.id`，不覆盖上传期间的新编辑。上传失败保留用户当前输入。

- [ ] **Step 6: 更新前端静态契约测试并验证**

在 `tests/test_web.py` 对真实脚本断言衍生牌标签、上传编号参数和项目元数据路径存在，不只用字符串代替行为测试；行为由 FastAPI 测试覆盖。运行：

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_web_projects.py tests/test_web.py -q`
Run: `for f in bwpdiy/web/static/editor-*.js; do node --check "$f" || exit 1; done`
Expected: 全部 PASS。

```bash
git add bwpdiy/web/app.py bwpdiy/web/static/editor-cards.js bwpdiy/web/static/editor-main.js tests/test_web_projects.py tests/test_web.py
git commit -m "feat(界面): 接入项目编号与衍生牌设置"
git push
```

### Task 3: 描述文本行首标点避让

**Files:**
- Modify: `bwpdiy/render/text.py`
- Test: `tests/test_text.py`

**Interfaces:**
- Consumes: 现有 `parse_items`、`_line_width`、`_layout_at_size`、`_fit`。
- Produces: 私有 `_NO_LINE_START` 字符集合与 `_carry_for_punctuation(current, item)` 辅助函数；公开 API 不变。

- [ ] **Step 1: 写固定字号的失败排版测试**

用现有 `rect_region` 和真实字体构造恰好容纳“甲乙”但不能容纳“甲乙，”的区域：

```python
def _wrapped_plain(lib, text):
    font = lib.font("desc", 36)
    width = math.ceil(font.getlength("甲乙")) + 1
    region = rect_region(0, 0, width, 200)
    lines = _layout_at_size(parse_items(text), font, region, True, lib=lib)
    return [_plain(line) for line, _, _ in lines]


def test_wrap_moves_previous_char_with_punctuation(assets_dir):
    lib = AssetLibrary(assets_dir)
    assert _wrapped_plain(lib, "甲乙，丙") == ["甲", "乙，丙"]
    assert _wrapped_plain(lib, "甲乙。”丙") == ["甲", "乙。”丙"]
    assert _wrapped_plain(lib, "甲\n，乙") == ["甲", "，乙"]  # 显式换行不改写
```

测试文件顶部补充 `import math`。

图标用例直接检查返回行的 `kind/value`：第二行必须以 `("icon", "ll", ...)` 开始，后接逗号，第一行不能以图标结尾；同时用 `_line_width` 确认每行未超宽。角标用例复用 `mask_row_runs`，断言移动后仍满足 span。

- [ ] **Step 2: 运行文本测试并确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_text.py -q`
Expected: 旧贪心换行产生行首标点，新用例 FAIL。

- [ ] **Step 3: 在换行分支携带前一项与连续标点**

定义设计文档列出的 `_NO_LINE_START`。仅当 `current` 非空、追加 `item` 超宽且 `item` 是禁止行首字符时进入：

```python
def _carry_for_punctuation(current, item):
    if not (item[0] == "char" and item[1] in _NO_LINE_START):
        return None
    cut = len(current)
    while cut and current[cut - 1][0] == "char" and current[cut - 1][1] in _NO_LINE_START:
        cut -= 1
    if cut:
        cut -= 1  # 连续标点之前的一个文字或图标一并下移
    if cut == 0:
        return None  # 极窄行交给更小字号，不制造空上一行
    return current[:cut], current[cut:] + [item]
```

`wrap_from` 收到 `(remaining, carried)` 后追加 `remaining`、推进行 y 并令 `current=carried`；后续区域边界与行数稳定迭代不变。无法携带时走现有普通换行/失败逻辑，最小字号兜底不变。

- [ ] **Step 4: 运行文本与渲染回归并提交**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_text.py tests/test_keyword_highlight.py tests/test_mech_render.py tests/test_pipeline.py tests/test_render_size.py -q`
Expected: PASS，公开返回结构和绘制 API 不变。

```bash
git add bwpdiy/render/text.py tests/test_text.py
git commit -m "fix(文本): 避免自动换行产生行首标点"
git push
```

### Task 4: 文档、精简复查与全量验证

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/terminology.md`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-09-14-bwpdiy-design.md`

- [ ] **Step 1: 同步当前行为文档**

记录 `project.yaml`、项目 ID 编辑、自动号段、衍生共用 `51–99`、`token` 字段、保存/上传响应 ID、历史版本同步和中立 `19999999`；术语表登记“项目 ID / 衍生牌 / 行首标点避让”。README 只保留简短功能说明，不追加冗长历史。

- [ ] **Step 2: 做删除清单式精简与安全检查**

检查本轮分支是否还有“无 ID 必回退”的旧提示、重复前端编号计算或失效测试；保留 schema 校验、全库冲突检查、路径约束、写锁、revision 防旧响应和版本组事务回滚。不得为精简删除这些安全行为。

- [ ] **Step 3: 全量验证**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q`
Run: `for f in bwpdiy/web/static/editor-*.js; do node --check "$f" || exit 1; done`
Run: `git diff --check`
Expected: 全量测试 PASS、所有脚本语法通过、无 whitespace 错误。

- [ ] **Step 4: 实际 GUI 冒烟**

用隔离的临时 `library` 启动开发版，依次验证：新建空白 ID 项目 → 新建主要式神得 `05101` → 新建普通/衍生/协战/衍生物与中立牌 → 上传图片使用最终 ID → 项目 ID 编辑 → 多版本仍归组 → 含标点和 `#ll` 的长描述预览无自动行首标点。停止临时服务，不触碰真实 `library/` 与 `~/.bwpdiy/layout.json`。

- [ ] **Step 5: 提交文档与收尾**

```bash
git add AGENTS.md docs/terminology.md README.md docs/superpowers/specs/2026-09-14-bwpdiy-design.md
git commit -m "docs(编号): 同步自动编号与文本排版约定"
git push
```
