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

- [x] M1~M3：render 渲染管线（PSD 官方素材、四类型×四框品、轮廓裁剪合成）+ store 卡牌库 + WebGUI 编辑器（双 tab、表单校验、实时预览、布局可视化调参、卡图上传定位）
- [x] v1.1：文本避让与自适应排版（碰撞轮廓避让、居中锚点偏移、先上移再缩字号）；破甲分离配置
- [x] v1.2：卡图上传与旋转、exe 自动更新（sha256 校验）、`[[关键字]]` 异色高亮、布局还原按钮
- [x] v1.2.2~1.2.3：文件名与卡名脱钩、式神卡多文件化与改名联动、协战双式神、式神 49 / 卡牌 299 上限、卡图 hash 命名
- [x] v1.2.4：卡名字体田氏颜体大字库 2.0（生僻字风格统一）
- [ ] M4：HTTP API + BWPro 集成文档；PNG 导出未做
- 二期：`#图标` 描述内嵌小图标、勾玉四色（黄/青/紫/红，BWPro 对战四位己方式神用）、协战双式神头像框、多牌框版型

## 美术资源来源与权利说明

`assets/` 中的牌框、等级勾玉、稀有度花标、数值角标、派系标、正负号等素材取自第三方整理的
《阴阳师百闻牌》卡面 PSD 模板（署名见 `assets/` 根目录 PSD 文件名）与早期位图资源，字体为
田氏颜体大字库 2.0 / 方正北魏楷书。上述素材的著作权归原游戏厂商与原素材作者所有，
本项目仅为个人学习与非商用 DIY 用途整理使用，不用于任何商业场景。
如权利方认为存在侵权，请在 GitHub 仓库提 issue 联系，核实后立即删除相关素材。

## 安全说明

本工具为本地单机应用：默认仅监听 `127.0.0.1`，服务端对请求做 Host 头校验（防 DNS rebinding），
卡图路径限制在项目目录内、图片有像素上限。请勿使用 `--host 0.0.0.0` 将服务暴露到局域网/公网——
本工具无鉴权机制，暴露后同网络主机可读取、修改、删除你的卡牌库。
