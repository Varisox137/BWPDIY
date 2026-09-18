# BWPDIY 项目级约定

《阴阳师百闻牌》DIY 卡牌工具。设计文档：`docs/superpowers/specs/2026-09-14-bwpdiy-design.md`；术语表：`docs/terminology.md`。用户级总纲见 `C:/Users/Varis/.kimi-code/AGENTS.md`，冲突时本文件优先。

## 架构红线

- 单包分层：`bwpdiy/render`（纯 PIL 渲染库）← `bwpdiy/store`（卡牌库+校验）← `bwpdiy/web`（FastAPI 编辑器）。**render 不得 import store/web**（BWPro 只 import `bwpdiy.render`，不能拖入 FastAPI）。
- `legacy/` 只读封存参考（旧版半成品源码与资源，无版本控制），任何情况下不修改、不删除。
- `library/` 是用户创作数据，gitignore，不提交。
- `assets/` 美术资源来自 legacy `basics/` 与 PSD 导出（`scripts/import_psd_assets.py` 生成）：命名约定牌框 `frames/{form,combat,spell,field,reinforce}_{框品}.png`（协战仅 norm）、等级 `levels/{base,evolve_star,level_{1,2,3}_yellow}.png`、稀有度 `rarity/{R,SR,SSR}{,_blue,_red}.png`+`reinforce_*`+`N.png`、数值标 `stats/{code}_{field}.png`、正负号 `signs/{plus,minus}.png`；masks 已废弃；旧位图资产封存 `assets/legacy/`。改动须同步 `docs/terminology.md`。

## 数据纪律

- 卡牌 yaml 分引擎段（与 BWPro 口径对齐，按类型分字段）与渲染段（`artwork.images` 列表，全可缺省）。schema 字段只增不改。
- 机制未实现不进数据；字段/枚举变更须同步设计文档与术语表。

## 工程纪律

- 测试命令（Windows Git Bash）：`PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q`
- 依赖用 uv（`uv add` / `uv sync`），不用 pip 直装。
- 中文 conventional commit；每次 commit 后 `git push`（失败不阻塞，汇报即可）；rebase/reset/分支操作先问。
- 大改动先 plan mode；批量新功能委托子代理，收尾全量测试由主上下文亲跑。
- 发布：pyinstaller 打包 `releases/BWPDIY-v<版本>.exe`（`scripts/build_exe.py`）+ `gh release create`；**同二级版本（前两位不变）的三级小更新发布时，删去该二级版本下的过往 GitHub release 与本地旧 exe，只保留最新版**。
