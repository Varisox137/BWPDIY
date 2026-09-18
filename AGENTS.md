# BWPDIY 项目级约定

《阴阳师百闻牌》DIY 卡牌工具。设计文档：`docs/superpowers/specs/2026-09-14-bwpdiy-design.md`；术语表：`docs/terminology.md`。用户级总纲见 `C:/Users/Varis/.kimi-code/AGENTS.md`，冲突时本文件优先。

## 架构红线

- 单包分层：`bwpdiy/render`（纯 PIL 渲染库）← `bwpdiy/store`（卡牌库+校验）← `bwpdiy/web`（FastAPI 编辑器）。**render 不得 import store/web**（BWPro 只 import `bwpdiy.render`，不能拖入 FastAPI）。
- `legacy/` 只读封存参考（旧版半成品源码与资源，无版本控制），任何情况下不修改、不删除。
- `library/` 是用户创作数据，gitignore，不提交。
- `assets/` 美术资源来自 legacy `basics/`，命名约定（牌框 `frames/frame_{zd/fs/xt/hj/xz}_{框品}_{版型}.png` 一期仅收 `*_norm_low.png`、蒙版 `masks/mask_*_low.png`，high 版型与 blue/black/red 框品原图留存 `frames/unprocessed/`）改动须同步 `docs/terminology.md`。

## 数据纪律

- 卡牌 yaml 分引擎段（与 BWPro 口径对齐，按类型分字段）与渲染段（`artwork.images` 列表，全可缺省）。schema 字段只增不改。
- 机制未实现不进数据；字段/枚举变更须同步设计文档与术语表。

## 工程纪律

- 测试命令（Windows Git Bash）：`PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q`
- 依赖用 uv（`uv add` / `uv sync`），不用 pip 直装。
- 中文 conventional commit；每次 commit 后 `git push`（失败不阻塞，汇报即可）；rebase/reset/分支操作先问。
- 大改动先 plan mode；批量新功能委托子代理，收尾全量测试由主上下文亲跑。
