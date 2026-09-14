# BWPDIY

《阴阳师百闻牌》DIY 卡牌工具：式神项目制卡牌库 + 服务端 PIL 卡面渲染 + WebGUI 编辑器。可独立使用，也可被 BWPro 以包导入方式调用渲染卡面。

## 快速开始

```bash
uv sync
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q
python -m bwpdiy   # 启动编辑器（M3 起可用）
```

## 文档

- 设计文档：`docs/superpowers/specs/2026-09-14-bwpdiy-design.md`
- 术语表：`docs/terminology.md`
- 项目约定：`AGENTS.md`

## 进度

- [x] 项目骨架与环境（2026-09-14）
- [ ] M1：render 渲染管线（卡图/蒙版/牌框/图标/纯文本排版）
- [ ] M2：store 卡牌库存取 + schema 校验
- [ ] M3：WebGUI 编辑器（列表/表单/实时预览/拖拽定位/导出）
- [ ] M4：HTTP API + BWPro 集成文档
- 二期：`[关键词]`/`#图标` 富文本、框品（墨染/琉璃/百炼）、多牌框版型
