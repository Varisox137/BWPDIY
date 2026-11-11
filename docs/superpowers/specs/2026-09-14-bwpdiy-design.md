# BWPDIY 设计文档

日期：2026-09-14；状态：已批准并持续维护。本文件说明总体设计，详细字段、布局参数与历史决策以 `docs/terminology.md`、`docs/integration.md` 和 `AGENTS.md` 为准。

## 1. 定位与架构

《阴阳师百闻牌》DIY 卡牌工具，兼具两种用途：

1. 独立 WebGUI：项目制卡牌库、卡面/头像/对局小卡/机制框编辑与导出。
2. 渲染库：BWPro 直接 `import bwpdiy.render`，传字典取得 PIL Image，不经过 HTTP 编辑器。

BWPro 官方数据库不收录用户 DIY 卡；DIY 数据独立存放，工具只提供格式校验与加载支持。

```
bwpdiy/
├── render/      # 纯 PIL；唯一供 BWPro 导入的层
├── store/       # 文件存储、版本、自动编号、schema 校验
├── web/         # FastAPI API 与 vanilla JS 编辑器
└── __main__.py  # 编辑器入口
assets/          # 运行时美术资源与归档
library/         # 用户创作数据，不提交
legacy/          # 只读旧版参考
```

依赖方向为 render ← store ← web。基础包只依赖 Pillow；Web 依赖可选。技术栈为 Python 3.12+、uv、Pillow、PyYAML、FastAPI/Uvicorn、无构建 vanilla JS、pytest。

## 2. 数据模型

项目结构：

```
library/<项目>/
├── project.yaml     # 可选三位 id 与 release_date
├── shikigami/       # 主要式神
├── cards/           # 其他卡牌与衍生物式神
└── images/          # 卡图
library/mechanisms/  # 跨项目机制共享池
```

文件名与卡名脱钩；主要式神按 name 引用并在改名时联动。主要式神上限 49，卡牌/衍生物上限 299，多版本按组计。卡牌按 id+name、机制按 name 归组版本，同组共享 layout/artwork。

保存或上传时由 store 自动补空白 ID：主要式神使用 `1<项目ID><两位序号>`，普通所属卡追加 `01–20`，协战追加 `21–50`，衍生牌与衍生物式神共用 `51–99` 从两端取号，中立非协战牌从 `19999999` 递减。项目 ID 从 `051–999` 取空号。GUI 在新建普通非式神卡时确定衍生标记，衍生牌默认无稀有度。完整规则与事务边界见 `AGENTS.md`。

卡牌 YAML 分引擎段与渲染段：

```yaml
type: 法术
name: 示例卡
id: "10030101"       # 可留空，保存/上传时补齐
level: 1
rarity: R
shikigami: 示例式神
description: 造成3点伤害，获得#hl。
artwork:
  images:
    - path: 10030101.png
      offset_x: 0
      offset_y: 0
      scale: 1.0
      rotate: 0
```

引擎字段与 BWPro 对齐，schema 字段只增不改，机制未实现不进数据。`artwork` 可整段缺省；异画只改变立绘与各自变换，不改变布局。`layout` 为单卡稀疏覆盖，`portrait` 为主要式神头像变换；`burst/status` 仅临时渲染字段，不持久化。

## 3. 渲染管线

大卡合成顺序：

1. 卡图旋转、cover 缩放、中心 offset 取景；按牌框实心轮廓向内腐蚀后的区域裁掉框外卡图。
2. 叠加牌框，再绘制卡名、稀有度、脚注。
3. 绘制等级、派系、数值/爆能/特殊状态图标与可选协战双式神框。
4. 描述文本自动排版并避让角标碰撞轮廓。
5. 最后绘制数值与爆能数字，按全部可见元素的透明边界紧致导出。

等级为底座、觉醒星、纯色圆、勾玉四层；数字与符号使用五色位图。描述支持 `[[关键字]]`、`#xx` 内嵌图标、行首标点避让和 `text_layout=smart/wrap/off`。

`render_card/render_entity/render_portrait` 支持 `width/height` 原生重绘，不是默认成品二次缩放。`render_mechanism` 另支持 `chars_per_line/font_scale`，框高随内容变化。接口和尺寸规则见 `docs/integration.md`。

## 4. WebGUI

主 tab 为「卡牌库」「对局预览」「全局布局设置」。前端按共享、卡牌、对局、机制、布局、入口六段经典脚本加载，不引入框架。

- 卡牌库：项目、主要式神、卡牌/衍生物和机制 CRUD；表单即时校验、实时预览、卡图鼠标调整与撤回、版本管理、卡图/头像/小卡导出。
- 对局预览：临时调整大卡爆能/特殊状态与小卡等级、数值颜色、能量、倒计时、气绝；不写盘、不置脏，离开使旧请求失效。
- 布局设置：六类型 × 四框品、对局小卡和三类机制框独立调参；单卡布局为对应全局布局的稀疏覆盖。
- 扩展选项：分别控制布局入口与高级标记/对局功能；隐藏控件不清空已保存数据。

卡图与头像预览分别调度，每通道只保留一个在途请求和最新待办，防止鼠标轨迹排队与慢响应逆序覆盖。所有本地写操作串行，未保存切换须提示。

## 5. 运行与集成

默认只监听回环地址；正式版端口 8630，开发版 8631。连续 2h 无活动自动退出，支持手动退出与更新前清理未引用图片。日志、端口占用处理和自动更新规则见 `AGENTS.md`。

BWPro 只导入 render 层，资源根与卡图根需显式配置。资源、字段、缓存、异常和最小自检见 `docs/integration.md`。

## 6. 测试与发布

测试分 schema/store、纯 PIL 渲染、FastAPI/WebGUI 与启动/更新四层。标准命令：

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q
```

提交使用中文 conventional 格式并推送。发布由 `scripts/build_exe.py` 生成单文件 exe 与 SHA256；包内默认布局变更时必须在最近更新首条加粗提示。

## 7. 后续事项

- BWPro 现有卡牌可逐张补 `artwork` 并调 offset/scale；整段缺省即可居中渲染，无迁移阻塞。
- BWPro 美术资产目录与卡图相对路径基准由调用方配置。
- 赏金大角标待补素材与实现；`#sj` 小图标已可用。
- 后续候选：项目备份/批量导出、多卡图管理、二期更多版型。
