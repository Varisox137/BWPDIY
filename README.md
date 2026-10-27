# BWPDIY

《阴阳师百闻牌》DIY 卡牌工具：式神项目制卡牌库 + 服务端 PIL 卡面渲染 + WebGUI 编辑器。可独立使用，也可被 BWPro 以包导入方式调用渲染卡面。

## 快速开始

```bash
uv sync
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q
python -m bwpdiy   # 开发版启动编辑器（默认 http://127.0.0.1:8631；打包正式版默认 8630）
                   # 可选 --host/--port 改监听地址端口；--no-browser 禁用自动打开浏览器；
                   # --no-idle-stop 关闭闲置 2h 自动终止（开发用，打包 exe 默认保留）
                   # 端口占用时显示 PID，仅在交互终端回车确认后关闭占用进程并启动
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

- 已完成 M1~M3：渲染管线、卡牌库与 WebGUI 编辑器；当前为 v1.7.2。
- 支持多种卡面与机制框、多版本项目、布局编辑、卡图/头像/对局小卡导出、原生尺寸渲染及 exe 自动更新。
- 历史更新请查看工具内「最近更新」或 [GitHub Releases](https://github.com/Varisox137/BWPDIY/releases)。
- 后续：M4（HTTP API + BWPro 集成文档）、二期多牌框版型。

## 美术资源来源与权利说明

`assets/` 中的牌框、等级勾玉、稀有度花标、数值角标、派系标、正负号等素材取自第三方整理的
《阴阳师百闻牌》卡面 PSD 模板（署名见 `assets/` 根目录 PSD 文件名）与早期位图资源，字体为
田氏颜体大字库 2.0 / 方正北魏楷书。上述素材的著作权归原游戏厂商与原素材作者所有，
本项目仅为个人学习与非商用 DIY 用途整理使用，不用于任何商业场景。
如权利方认为存在侵权，请在 GitHub 仓库提 issue 联系，核实后立即删除相关素材。

## 运行日志与问题反馈

每次启动会在运行目录 `logs/` 写一份单次运行日志 `bwpdiy-<日期时间>.log`（保留最近 10 次，并自动删除超过 7 天的旧日志；目录不可写时回退系统临时目录 `bwpdiy-logs/`），记录版本、启动参数、服务与自动更新全过程。反馈问题（尤其更新失败/卡死）时请附上该次运行的日志文件。

## 安全说明

本工具为本地单机应用：默认仅监听 `127.0.0.1`，服务端对请求做 Host 头校验（防 DNS rebinding），
卡图路径限制在项目目录内、图片有像素上限。请勿使用 `--host 0.0.0.0` 将服务暴露到局域网/公网——
本工具无鉴权机制，暴露后同网络主机可读取、修改、删除你的卡牌库。
