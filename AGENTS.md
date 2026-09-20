# BWPDIY 项目级约定

《阴阳师百闻牌》DIY 卡牌工具。设计文档：`docs/superpowers/specs/2026-09-14-bwpdiy-design.md`；术语表：`docs/terminology.md`。用户级总纲见 `C:/Users/Varis/.kimi-code/AGENTS.md`，冲突时本文件优先。

## 架构红线

- 单包分层：`bwpdiy/render`（纯 PIL 渲染库）← `bwpdiy/store`（卡牌库+校验）← `bwpdiy/web`（FastAPI 编辑器）。**render 不得 import store/web**（BWPro 只 import `bwpdiy.render`，不能拖入 FastAPI）。`bwpdiy/updater.py`（exe 自动更新：GitHub latest release 检查 + 一键下载替换重启）仅 web 层引用。
- `legacy/` 只读封存参考（旧版半成品源码与资源，无版本控制），任何情况下不修改、不删除。
- `library/` 是用户创作数据，gitignore，不提交。
- `assets/` 美术资源来自 legacy `basics/` 与 PSD 导出（`scripts/import_psd_assets.py` 生成）：命名约定牌框 `frames/{form,combat,spell,field,reinforce}_{框品}.png`（协战仅 norm）、等级 `levels/{base,evolve_star,level_{1,2,3}_yellow}.png`、稀有度 `rarity/{R,SR,SSR}{,_blue,_red}.png`+`reinforce_*`+`N.png`、数值标 `stats/{power,health,combat_shield,combat_fragile_{1,2},field_intensity}.png`（力量/生命全类型共用，无类型前缀）、正负号 `signs/{plus,minus}.png`；masks 已废弃；旧位图资产封存 `assets/legacy/`。改动须同步 `docs/terminology.md`。

## 数据纪律

- 卡牌库结构（v1.2.2）：`library/<项目>/shikigami/*.yaml`（式神卡，一式神一文件、上限 49）+ `cards/*.yaml`（≤299）+ `images/`（上传卡图按 `<id 或卡名><ext>` 命名，改 id 不重命名已有卡图）；文件名与卡名脱钩（卡名=文件内 name），式神改名由 store 层联动更新同项目引用。
- 卡牌 yaml 分引擎段（与 BWPro 口径对齐，按类型分字段；协战所属式神为 `shikigami1`/`shikigami2`）与渲染段（`artwork.images` 列表，全可缺省）。schema 字段只增不改。
- 描述文本（description）支持 `[[关键字]]` 高亮标记（双英文方括号、括号不绘制、按框品异色；单 [ ] 为字面字符；配对校验见 `render/text.py` parse_keyword_segments）与 `#xx` 内嵌图标（v1.3.0，两位拼音首字母代码见 `render/text.py` ICON_CODES，未知代码报错；派系图标墨染框用 `_black` 变体；大小=字号×desc 区 `icon_scale`，与相邻文字间自动加四分之一宽空格（0.25em），宽度计入换行与居中）。
- 机制未实现不进数据；字段/枚举变更须同步设计文档与术语表。

## 工程纪律

- 测试命令（Windows Git Bash）：`PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q`
- 依赖用 uv（`uv add` / `uv sync`），不用 pip 直装。
- 中文 conventional commit；每次 commit 后 `git push`（失败不阻塞，汇报即可）；rebase/reset/分支操作先问。
- 大改动先 plan mode；批量新功能委托子代理，收尾全量测试由主上下文亲跑。
- 发布：pyinstaller 打包 `releases/BWPDIY-v<版本>.exe`（`scripts/build_exe.py`，同时生成 `<exe>.sha256` 校验文件）+ `gh release create`（exe 与 .sha256 两个资产都要上传，客户端下载后强制校验）；**同二级版本（前两位不变）的三级小更新发布时，删去该二级版本下的过往 GitHub release 与本地旧 exe，只保留最新版**。
