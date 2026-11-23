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

实验性 Pyodide 在线本地版原型（首次需要联网；不参与 exe 打包）：

```bash
python prototype/pyodide/server.py   # http://127.0.0.1:8640/
```

Termux 可执行 `pkg install git python`，然后在干净的仓库副本中运行
`./scripts/termux_server.sh`。脚本会先以 `git pull --ff-only` 更新再启动，并记录到
`logs/bwpdiy-launcher-*.log`；拒绝覆盖本地改动。可用 `BWPDIY_PORT`、`BWPDIY_BRANCH`、
`BWPDIY_REMOTE`、`BWPDIY_REPO_DIR`、`BWPDIY_PYTHON` 环境变量调整默认值。

初始化完成后自动生成预览，加载进度与失败原因显示在中央区域。同源程序、素材和固定版本 Pyodide 在首次下载后按版本缓存，重复打开及断网重载不重新下载；更新部署时会随缓存版本更新。

支持原版三主标签页与配色、单卡/机制编辑、对局小卡与头像合成、按类型和框品调整全局布局、鼠标/触屏手势调整卡图、PNG 导出及 JSON 草稿备份。触屏双指只在卡图上调整缩放/旋转，不控制页面整体缩放。桌面保留三栏，平板与手机采用响应式布局；低负载预览和浏览器存储容量/持久保护状态仅在本机处理。表单、卡图和布局仅保存在浏览器 IndexedDB，程序与素材仅缓存于浏览器 Cache Storage；服务器不提供渲染或写盘 API。

## 文档

- BWPro 渲染集成：`docs/integration.md`
- 设计文档：`docs/superpowers/specs/2026-09-14-bwpdiy-design.md`
- 术语表：`docs/terminology.md`
- 项目约定：`AGENTS.md`

## 进度

- 已完成 M1~M4：渲染管线、卡牌库、WebGUI 编辑器与 BWPro 集成契约；当前为 v1.8.8。
- 支持项目与卡牌自动编号、描述三态智能排版与行首标点避让、多种卡面与机制框、多版本项目、按框品独立布局、八色勾玉、五色位图数字与符号、逐条目内嵌派系样式、大卡特殊状态预览、独立对局预览、大卡爆能及小卡四色边框、能量/倒计时/气绝组件、卡图/头像/对局小卡导出、原生尺寸渲染及 exe 自动更新；侧栏提供逐历史日期的卡组数量与稀有度分布校验。
- 历史更新请查看工具内「最近更新」或 [GitHub Releases](https://github.com/Varisox137/BWPDIY/releases)。
- 后续：项目备份/批量导出、多卡图管理、二期多牌框版型。

## 美术资源来源与权利说明

`assets/` 中的牌框、等级勾玉、稀有度花标、数值角标、派系标、位图数字与正负号等素材取自第三方整理的
《阴阳师百闻牌》卡面 PSD 模板（署名见 `assets/` 根目录 PSD 文件名）与早期位图资源，字体为
田氏颜体大字库 2.0 / 方正北魏楷书。上述素材的著作权归原游戏厂商与原素材作者所有，
本项目仅为个人学习与非商用 DIY 用途整理使用，不用于任何商业场景。
如权利方认为存在侵权，请在 GitHub 仓库提 issue 联系，核实后立即删除相关素材。

## 运行日志与问题反馈

每次启动会在运行目录 `logs/` 写一份单次运行日志 `bwpdiy-<日期时间>-<PID>.log`（保留最近 10 次，并自动删除超过 7 天的旧日志；目录不可写时回退系统临时目录 `bwpdiy-logs/`），记录版本、启动参数、服务与自动更新全过程；文件另含按钮、字段变更及写盘 DEBUG 事件（PIL 的 PNG 字节流 DEBUG 不记录），控制台仍只显示 INFO 及以上。反馈问题（尤其更新失败/卡死）时请附上该次运行的日志文件。

## 安全说明

本工具为本地单机应用：默认仅监听 `127.0.0.1`，服务端对请求做 Host 头校验（防 DNS rebinding）并拒绝浏览器跨站写操作，
卡图路径限制在项目目录内、图片有像素上限。请勿使用 `--host 0.0.0.0` 将服务暴露到局域网/公网——
本工具无鉴权机制，暴露后同网络主机可读取、修改、删除你的卡牌库。
