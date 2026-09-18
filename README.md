# BWPDIY

《阴阳师百闻牌》DIY 卡牌工具：式神项目制卡牌库 + 服务端 PIL 卡面渲染 + WebGUI 编辑器。可独立使用，也可被 BWPro 以包导入方式调用渲染卡面。

## 快速开始

```bash
uv sync
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q
python -m bwpdiy   # 启动编辑器（http://127.0.0.1:8630，卡牌库/布局设置双 tab；旧 /layout 重定向至此）
                   # 可选 --host/--port 改监听地址端口；--no-browser 禁用自动打开浏览器
```

也可打包为单文件 exe（资源全内嵌，library/ 落在 exe 同级目录）：

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe scripts/build_exe.py   # 产物 releases/BWPDIY-v<版本>.exe
```

## 文档

- 设计文档：`docs/superpowers/specs/2026-09-14-bwpdiy-design.md`
- 术语表：`docs/terminology.md`
- 项目约定：`AGENTS.md`

## 进度

- [x] 项目骨架与环境（2026-09-14）
- [x] M1：render 渲染管线（卡图/蒙版/牌框/图标/纯文本排版）
- [x] M1.5：布局配置系统 + Web 配置工具（layout.json 可视化调参/实时预览（样卡数值/式神名/子类型/描述可编辑）/按类型开关元素）
- [x] M2+M3 骨架：store 卡牌库存取 + schema 校验；WebGUI 编辑器主体（卡牌库/布局设置双 tab——项目与卡牌 CRUD、按类型表单+即时校验+实时预览、布局可视化调参）
  - 未做：卡图上传、预览内拖拽/滚轮定位卡图（offset/scale 写回）、单卡/批量 PNG 导出
- [x] v1.0：PSD 官方素材全面替换（四类型×四框品牌框/勾玉等级标/按类型数值角标/贴图正负号/裁单枚花标稀有度）；
  新合成管线（卡图→叠框→裁框外→元素→tightest bbox 导出，masks 废弃）；框品字段 frame_variant；
  顶栏「扩展选项」（布局编辑/N 稀有度默认不开放）；exe 启动自动开浏览器；旧素材归档 assets/legacy/
- [ ] M4：HTTP API + BWPro 集成文档
- 二期：`[关键词]`/`#图标` 富文本、勾玉四色（黄/青/紫/红，BWPro 对战四位己方式神用）、协战双式神头像框、多牌框版型
