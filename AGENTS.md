# BWPDIY 项目级约定

《阴阳师百闻牌》DIY 卡牌工具。现行设计见 `docs/superpowers/specs/2026-09-14-bwpdiy-design.md`，BWPro 集成契约见 `docs/integration.md`，术语见 `docs/terminology.md`。用户级总纲见 `C:/Users/Varis/.kimi-code/AGENTS.md`，冲突时本文件优先。远期方向为 DIY 分享交流社区平台并评估内嵌 BWPro；不得因此擅自在当前在线本地版加入账号、作品上传或社区写接口。

## 架构红线

- 分层方向：`render`（纯 PIL）← `store`（卡牌库与校验）← `web`（FastAPI 编辑器）。`render` 不得 import `store/web`；基础包只依赖 Pillow，PyYAML/FastAPI/Uvicorn 属 `web` 可选依赖。
- 前端无构建：`editor.html` 只保留结构，`editor.css` 与 `editor-{core,cards,battle,mech,layout,tutorial,main}.js` 按固定顺序以经典脚本加载。共享全局词法依赖不变，禁止擅自改为 ES Module 或引入框架；Node 测试按 HTML 顺序拼接真实脚本。
- `legacy/` 只读封存；`library/` 是用户创作数据，gitignore，不提交。
- `prototype/pyodide/` 是隔离的在线本地版实验：Pyodide + Pillow 在 Web Worker 内运行，静态服务器仅在固定根路径白名单提供文件和运行时包（排除 PSD），旧路径/目录/未知 API 均 404；运行时包进程内只构建一次并按 2 MiB 分包（`runtime.json` + `runtime-chunks/`），不提供整包下载端点；正常资源默认全局限流 120/分钟、突发 30，异常请求使用独立配额（10s 内 8 次、冷却 300s），不得消耗正常资源配额或使异常冷却拦截正常资源；连接 8、请求头超时 20s/响应 120s，安全边界见 `docs/online-security.md`。来源默认只取 socket 对端并忽略转发头，`--client-ip-header` 仅供可信代理覆盖写入单个 IP 时启用。不得加入渲染/写盘 API 或暴露仓库其他目录；唯一例外是 `/api/log-admin/` 提取码鉴权的只读日志接口，运维页 `/log-admin/` 与 API 均禁缓存且不经 Service Worker；不参与 exe 打包。
- 在线运行时使用 `scripts/build_online_fonts.py` 预生成的 `runtime-fonts.zip/json`：保留 GB2312、原字体常用非 CJK 字符及 FreeType CJK 蓝色区域参考字；构建固定 fontTools 版本并逐字比较多尺寸位图/边界/字宽，产物须确定性。服务器校验后按原 `assets/fonts` 路径替换，桥接提供字符清单，前端显示缺字提示。正式字体变更必须重建两产物并递增 `RUNTIME_CACHE`；Termux 运行无需 fontTools。生僻字完整回退仍待实现，不得声称在线支持原字体全集。
- 原型作品、卡图与全局布局只存浏览器 IndexedDB（`storage.js` 同一 `drafts` store 的 `work:<uuid>`、`library-index`、`global-layout`；旧 `current` 仅启动时迁移），程序与素材只存浏览器 Cache Storage（`sw.js`）；两者均不得落服务器。`library.js` 管理按项目分组的多作品、串行自动保存、schema 1 单作品与 schema 2 整库备份；整库含全部卡图及一份布局，导入合并并重建内部 ID，单作品不覆盖布局。切换作品后丢弃旧作品的渲染响应。界面静态程序、运行时 ZIP 清单/分包、固定版本 Pyodide CDN 分别使用 `RESOURCE_CACHE`、`RUNTIME_CACHE`、`PYODIDE_CACHE` 缓存优先；缓存 miss 必须 `fetch(..., {cache:"reload"})` 避免复用旧 HTTP 缓存，界面升级不得删除运行时与 Pyodide。修改界面/Worker/Service Worker 递增 `RESOURCE_CACHE`，修改运行时 ZIP 内容递增 `RUNTIME_CACHE`，两者都涉及时同时递增；缓存写入通过 `waitUntil` 后台完成，不得阻塞响应流。清缓存不得清作品或布局。
- 原型界面沿用正式工具三主标签页、米白侧栏/深灰预览/金色选中态。`layout.js` 按类型×框品修改现有布局结构并独立保存；卡图鼠标/触屏预览最多一个在途渲染与最新待办，禁止回放轨迹。
- 原型桌面保留三栏，平板预览置顶双栏、手机单栏且可折叠卡面，并提供卡库/编辑/机制/更多底部导航；类型入口切换最近同类作品或新建，不得原地改写作品类型。触屏单指移动/双指缩放旋转，可锁定手势、全屏预览，并通过 ± 长按按钮和精细模式调整数值。`mobile.js` 负责这些移动交互及软键盘避让，锁定时卡图区域允许页面滚动。描述快捷输入在光标处插入，IME 组词期间暂停预览与草稿写入，结束后统一刷新。QQ/微信等内置浏览器导出使用长按保存弹窗，默认透明，可在浏览器内生成白底副本；不得上传作品。运行记录与导出弹窗可复制不含卡名、描述和卡图数据的诊断信息。低负载模式仅降低连续拖拽的大卡预览，松手与导出恢复完整质量；`localStorage` 只存低负载、手势锁定与教程完成偏好。`tutorial.js/css` 提供真实控件互动引导，教程期间暂停 IndexedDB 写入并禁止切换/新建/删除/导入真实作品，退出恢复快照，完成后由用户选择保留或恢复。存储容量/持久保护用浏览器 Storage API 查询，持久化只能由用户点击请求，不得把配额或授权结果当作保证。
- 资源命名与目录以 `docs/asset-mapping-v1.0.md` 和 `docs/terminology.md` 为准；改动资源引用须同步文档。`assets/legacy/`、`assets/psd_export/` 不进 exe。

## 启动、日志与更新

- `scripts/termux_server.sh` 仅用于 Pyodide 原型：校验干净 Git 部署副本后拉取 `main`，以 Python ≥3.12 标准库启动静态服务，不安装正式工具依赖；默认仅监听 `127.0.0.1:8640`，launcher 日志写入 `logs/`。原型运行日志复用 `runlog`，`/log-admin/` 提供只读 GUI；提取码每 10 分钟轮换并原子写入 `logs/.log-access-token`，只向交互终端显示秘密，日志与 localStorage 不记录提取码。
- 正式版默认端口 8630，源码开发版 8631，`--port` 可覆盖。回环端口占用时显示服务/PID，只有交互 TTY 空回车确认才 taskkill 对应进程；非 TTY 或取消不得杀进程。
- 正式版首行打印版本和包内 UTC 秒级打包时间（ISO 8601），开发版只打印版本。
- 每次启动写 `<运行目录>/logs/bwpdiy-<日期时间>-<PID>.log`；exe 取 exe 目录，开发取 cwd，不可写时回退临时目录 `bwpdiy-logs/`。保留最近 10 次并删除超过 7 天的旧日志。
- root 同时写文件和控制台：文件 DEBUG+，控制台 INFO+；屏蔽 PIL 字节流 DEBUG，uvicorn access 降为 WARNING。控制台仅交互 TTY 给级别标签着色。启动、更新、异常、GUI 操作与本地写入须落日志；正文只记长度。
- 连续 2h 无 HTTP 操作自动退出；更新检查/进度轮询不计活动。`create_app(idle_timeout=, on_idle=, on_shutdown=)` 支持注入，≤0 关闭空闲终止。
- 顶栏「退出DIY工具」统一检查未保存状态，`POST /api/shutdown` 记录「手动按钮关闭」并调用回调；退出前清理未引用卡图。
- 自动更新使用 GitHub latest release，GUI 加载即查一次、此后每 1min 复查；下载显示进度、总时限 600s、强制 SHA256 校验，失败删除半截文件并保留手动下载入口。更新任务进程内互斥。

## 数据与存储

- 项目结构：`library/<项目>/project.yaml + shikigami/*.yaml + cards/*.yaml + images/`。主要式神存 `shikigami/`，其他卡牌及有所属式神的衍生物式神存 `cards/`；机制统一存 `library/mechanisms/*.yaml`，项目名保留字 `mechanisms`。机制缺省 `global=true`；非全局含 `project` 与可选 `shikigami` 归属，同组版本共享，项目/式神改名同步。
- `project.yaml` 可含全库唯一三位 `id` 与合法 `release_date`（YYYYMMDD）。文件名与卡名脱钩；主要式神改名由 store 联动更新同项目引用。
- 数量上限按版本组计：主要式神 49、卡牌/衍生物 299。侧栏各栏目最多完整展开 8 项，第 9 项起内部滚动。主要式神按各历史日期校验至少 4R/3SR/1SSR；协战牌与衍生物式神不参与。
- 自动编号由 store 在保存/上传时完成，前端不计算，已有手动 ID 保留：
  - 项目 ID 从 `051–999` 取全库最小空号；改项目 ID 不迁移旧卡。
  - 主要式神为 `1<项目ID><01–99>`；普通所属卡为 `<式神六位ID><01–20>`；协战取较小式神 ID 前缀与 `21–50`。
  - 衍生牌与衍生物式神共用 `51–99`，分别递增/递减，无固定分界；中立非协战牌从 `19999999` 起全库递减。完整 ID 跳过全库占用。
  - 非协战所属卡可用两位简写，所属式神 ID 为六位时保存展开；协战/中立卡不展开。
- 卡牌按 `id+name`、机制按 `name` 归组版本。`version_date` 为合法 YYYYMMDD；新版本文件名为 `基础stem@日期`。同组共享 `layout/artwork`，保存任一版本同步；带 @ 文件改日期会重命名。
- 新建主要式神日期优先项目 `release_date`，其余留空取当天；其他新卡优先所属主要式神最早日期。新建非全局机制空白日期优先所属式神最早版本日期，项目级机制取项目 `release_date`，均无则取当天；已有条目不因项目日期变化回溯。
- 卡牌类型创建后固定。上传卡图按最终 `<id><ext>` 落盘，目标被其他组引用时自动加后缀；改 ID 不主动重命名旧图。无 ID 历史数据补号时保留原回退图引用与变换。
- 项目级 YAML 快照保护保存联动，失败回滚；web 本地写操作串行。图片原子写入，写图后保存失败只恢复图片，不回滚此前已写入的项目/所属式神 YAML。
- 正常退出、闲置终止、手动退出和更新替换前调用 `cleanup_unused_images`；任一 YAML 不可读或 images/ 为外链时跳过该项目，路径先 resolve 比较。
- schema 字段只增不改，机制未实现不进数据。stat 数值最多 10 位；artwork/portrait 数值有限；布局数值有限且绝对值 ≤8192。2.0 仅接受当前 YYYYMMDD 日期与机制字段，不再归一短横线日期或静默清除早期 `marks`。
- GUI 在新建非式神、非协战卡时选择 `token: true` 作为衍生牌，创建后不在右栏切换；衍生牌默认无稀有度。衍生物式神用类型与 `shikigami`，支持 `special_type`，不提供头像预览/参数/导出。
- `burst/status` 仅临时渲染字段，不进 store schema 或持久化。爆能以独立 `pos` 定位于大卡右上角，旧等级相对 `offset` 加载时按新旧默认位置差迁移；特殊状态仍随等级锚点。`inline_faction_style` 为 1/2/3，缺省 1；扩展控件隐藏时不清空已保存值。

## 布局与渲染

- 开发版与正式版统一读写 `$HOME/.bwpdiy/layout.json`，缺失回退包内 `bwpdiy/render/default_layout.json`。包内默认布局变更的版本必须在「最近更新」首条加粗提示用户重新调整本地布局。
- 六卡牌类型均按「类型 × 框品」完全解耦保存 `elements/text_regions`；`frame_variants.{blue,black,red}` 为稀疏覆盖，加载补全、保存剔同。单卡 `layout` 再覆盖实际框品全局布局，不跨类型传播。
- 对局布局直接按当前 96×144 结构加载并补齐缺省元素；2.0 起不再迁移 64×96 或 `right_top` 早期配置。爆能旧 `offset` 的 1.8.8 迁移仍保留。
- 大卡默认在 512×512 工作画布合成，最终按全部可见元素的 tightest alpha bbox 原尺寸返回；布局绝对 x 以实际牌框左缘为原点，y 以画布顶为原点。`crop=False` 仅用于内部/测试。
- `render_card/render_entity/render_portrait` 支持可选 `width/height`：单参数按默认紧致比例推算，双参数允许取整 1px 误差；必须为正整数，边长 ≤8192、总像素 ≤6400 万。按目标原生重绘所有元素，禁止先渲染默认成品再 resize；无参数路径逐像素不变。
- `render_mechanism` 支持 `chars_per_line` 与 `font_scale`，不要求保持比例：字数决定文本宽与框宽；倍率同步缩放文字、文本区、框宽/横向偏移和框行高，不缩放角标。
- 普通大卡静态绘制命令/层序列按原顺序重放，LRU 最多 8 条，不合并成单一覆盖层；缩放卡图中间图 LRU 总像素 ≤6400 万。
- 小卡等级 0–3；0 仅绘制底框和卡图。小卡边框支持 norm/blue/black/red，state 缺省继承大卡 `frame_variant`，未设置则为 norm；对局页与小卡布局预览可临时覆盖，布局页四色共用同一小卡布局段。普通 `countdown` 与 `defeated_countdown` 均允许 0，后者另接受精确字符串 `infinity`；能量允许 0。渲染库允许能量与倒计时共存，倒计时后绘制；气绝保留能量、隐藏普通倒计时，仅灰化底框和卡图，气绝组件最后绘制。
- 小卡战力/乏力读 `stats/combat_power.png`、`stats/weak.png`；只有文本内嵌 `#zl/#fl` 使用 `icons/` 小图。负战力/负护甲保留负号并使用乏力/破甲图标，正值不带加号；两项分别通过 `sign_size_minus` 调整负号尺寸，缺省为字号一半；符号与数字整体居中并计入紧致边界。
- 描述支持 `[[关键字]]` 高亮与 `#xx` 内嵌图标。双括号从左往右匹配，未匹配按字面文本；高亮内不嵌套解析双括号，# 图标仍解析。未知图标代码报错。
- 图标高为字号 × desc `icon_scale`，相邻文字间加八分之一宽空格；图标宽度参与换行和居中。自动换行与水平居中按整行文字掩膜的最紧边界测宽，保留段内 advance/字距，仅排除最外侧字框空白。卡牌与机制自动换行须避免闭合/句读标点落在行首，显式换行后的用户标点保留。
- 卡牌 `text_layout=smart/wrap/off`，缺省 `smart`；`wrap` 仅自动换行/缩字号，`off` 仅显式换行、固定最大字号且不避让角标。描述行间空白随实际字号取字高的 1/3。smart 优先避免闭标点/句读位于行首及比较/运算符、前引号或开括号留在行尾，再在同字号且不增加行数时避免高亮短语跨行、内嵌图标位于行首；会增加行数则回退。最终字号与行数确定后，smart 缩窄临时文本区至同版式可容纳的最小整数宽度以均衡行长，不增加断行罚项、不改布局。其余规则与阈值见术语表，机制不支持此字段。
- 文本、数字、描边/位图、轮廓裁剪等校验与安全逻辑不属于可精简的冗余。

## WebGUI 行为

- 三个主 tab：制作、对局预览、高级布局（单卡模式仍显示单卡布局设置）。布局与对局页分别由「手动调整布局」「扩展功能」控制显隐；旧独立 `/layout` 路由已移除，仅保留 `/#layout` hash 深链。
- 桌面互动教程使用 `editor-tutorial.js/css` 和通用样卡预览接口构成纯内存沙盒：保存并恢复卡牌/机制表单与撤回状态，禁止保存、上传和项目操作，导出真实 PNG 后才完成；无项目也可运行，不得为教程创建或覆盖用户数据。首次欢迎优先于最近更新，localStorage 仅记录教程完成偏好。
- 再次点击已选条目取消选择：卡牌回所属式神、式神回项目、项目/机制回到仅显示全局机制。删除式神、专属牌或非全局机制后同样保留上一级项目/式神上下文并恢复对应表单，不自动选中兄弟项。全局机制选中时清空项目/式神/卡牌；非全局机制保留所属上下文，列表显示全局+当前项目+当前式神机制，其中非全局机制名称加粗。新建/取消全局按最近选择归属（式神优先），无项目则拒绝。
- 卡牌鼠标预览按 art/portrait 独立 `requestAnimationFrame` 调度：每通道每帧最多一次、取最新值，最多一个在途请求与一个最新待办，禁止排队回放轨迹；mouseup 强制最终预览，响应序号防逆序覆盖，切卡/清空使旧响应失效。普通输入 300ms 防抖。
- 对局预览使用独立会话和响应序号；离开页面使旧预览/导出失效。所有临时调参与导出不写盘、不置脏。
- 主要式神头像预览/参数需「扩展功能」与「头像框」同时开启；裸头像导出不依赖预览显隐，后端不得为衍生物式神返回头像。
- 前端 energy/countdown 互斥；协战无爆能，式神也无爆能。对局页等级、颜色、数值与状态均不写回卡牌。
- GUI 写盘在途或内联输入未完成时锁定其他交互；未保存切换须提示。保留 Host 校验、跨站写保护、卡图路径限制与图片像素上限，不要把本地服务暴露到公网。

## 工程纪律

- 测试：`PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q`；优先跑受影响测试，发布前全量验证。
- 依赖用 uv（`uv add` / `uv sync`），不用 pip 直装。
- 中文 conventional commit；每次 commit 后 `git push`（失败不阻塞，汇报即可）；rebase/reset/分支操作先问。
- 大改动先 plan mode；批量新功能委托子代理，收尾验证由主上下文亲跑。
- 发布：`scripts/build_exe.py` 生成 `releases/BWPDIY-v<版本>.exe` 与 SHA256，并写入 UTC 秒级打包时间；GitHub Release 同时上传两项资产。三级小更新删除同二级版本旧 Release。本地 releases 只留最近 5 个二级版本、每个二级版本只留最新 exe；SHA256 上传后本地一律删除。
