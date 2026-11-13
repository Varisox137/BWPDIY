# BWPDIY 项目级约定

《阴阳师百闻牌》DIY 卡牌工具。现行设计见 `docs/superpowers/specs/2026-09-14-bwpdiy-design.md`，BWPro 集成契约见 `docs/integration.md`，术语见 `docs/terminology.md`。用户级总纲见 `C:/Users/Varis/.kimi-code/AGENTS.md`，冲突时本文件优先。

## 架构红线

- 分层方向：`render`（纯 PIL）← `store`（卡牌库与校验）← `web`（FastAPI 编辑器）。`render` 不得 import `store/web`；基础包只依赖 Pillow，PyYAML/FastAPI/Uvicorn 属 `web` 可选依赖。
- 前端无构建：`editor.html` 只保留结构，`editor.css` 与 `editor-{core,cards,battle,mech,layout,main}.js` 按固定顺序以经典脚本加载。共享全局词法依赖不变，禁止擅自改为 ES Module 或引入框架；Node 测试按 HTML 顺序拼接真实脚本。
- `legacy/` 只读封存；`library/` 是用户创作数据，gitignore，不提交。
- 资源命名与目录以 `docs/asset-mapping-v1.0.md` 和 `docs/terminology.md` 为准；改动资源引用须同步文档。`assets/legacy/`、`assets/psd_export/` 不进 exe。

## 启动、日志与更新

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
- 新建主要式神日期优先项目 `release_date`，其余留空取当天；其他新卡优先所属主要式神最早日期。已有条目不因项目日期变化回溯。
- 卡牌类型创建后固定。上传卡图按最终 `<id><ext>` 落盘，目标被其他组引用时自动加后缀；改 ID 不主动重命名旧图。无 ID 历史数据补号时保留原回退图引用与变换。
- 项目级 YAML 快照保护保存联动，失败回滚；web 本地写操作串行。图片原子写入，写图后保存失败只恢复图片，不回滚此前已写入的项目/所属式神 YAML。
- 正常退出、闲置终止、手动退出和更新替换前调用 `cleanup_unused_images`；任一 YAML 不可读或 images/ 为外链时跳过该项目，路径先 resolve 比较。
- schema 字段只增不改，机制未实现不进数据。stat 数值最多 10 位；artwork/portrait 数值有限；布局数值有限且绝对值 ≤8192。
- GUI 在新建非式神、非协战卡时选择 `token: true` 作为衍生牌，创建后不在右栏切换；衍生牌默认无稀有度。衍生物式神用类型与 `shikigami`，支持 `special_type`，不提供头像预览/参数/导出。
- `burst/status` 仅临时渲染字段，不进 store schema 或持久化。`inline_faction_style` 为 1/2/3，缺省 1；扩展控件隐藏时不清空已保存值。

## 布局与渲染

- 开发版与正式版统一读写 `$HOME/.bwpdiy/layout.json`，缺失回退包内 `bwpdiy/render/default_layout.json`。包内默认布局变更的版本必须在「最近更新」首条加粗提示用户重新调整本地布局。
- 六卡牌类型均按「类型 × 框品」完全解耦保存 `elements/text_regions`；`frame_variants.{blue,black,red}` 为稀疏覆盖，加载补全、保存剔同。单卡 `layout` 再覆盖实际框品全局布局，不跨类型传播。
- 旧对局 `right_top` 加载时复制迁移到 `energy/countdown`；旧 64×96 对局布局只按 1.5 倍迁移一次。保留这些兼容迁移与校验，精简时不得删除。
- 大卡默认在 512×512 工作画布合成，最终按全部可见元素的 tightest alpha bbox 原尺寸返回；布局绝对 x 以实际牌框左缘为原点，y 以画布顶为原点。`crop=False` 仅用于内部/测试。
- `render_card/render_entity/render_portrait` 支持可选 `width/height`：单参数按默认紧致比例推算，双参数允许取整 1px 误差；必须为正整数，边长 ≤8192、总像素 ≤6400 万。按目标原生重绘所有元素，禁止先渲染默认成品再 resize；无参数路径逐像素不变。
- `render_mechanism` 支持 `chars_per_line` 与 `font_scale`，不要求保持比例：字数决定文本宽与框宽；倍率同步缩放文字、文本区、框宽/横向偏移和框行高，不缩放角标。
- 普通大卡静态绘制命令/层序列按原顺序重放，LRU 最多 8 条，不合并成单一覆盖层；缩放卡图中间图 LRU 总像素 ≤6400 万。
- 小卡等级 0–3；0 仅绘制底框和卡图。普通 `countdown` 与 `defeated_countdown` 均允许 0，后者另接受精确字符串 `infinity`；能量允许 0。渲染库允许能量与倒计时共存，倒计时后绘制；气绝保留能量、隐藏普通倒计时，仅灰化底框和卡图，气绝组件最后绘制。
- 小卡战力/乏力读 `stats/combat_power.png`、`stats/weak.png`；只有文本内嵌 `#zl/#fl` 使用 `icons/` 小图。
- 描述支持 `[[关键字]]` 高亮与 `#xx` 内嵌图标。双括号从左往右匹配，未匹配按字面文本；高亮内不嵌套解析双括号，# 图标仍解析。未知图标代码报错。
- 图标高为字号 × desc `icon_scale`，相邻文字间加八分之一宽空格；图标宽度参与换行和居中。自动换行与水平居中按整行文字掩膜的最紧边界测宽，保留段内 advance/字距，仅排除最外侧字框空白。卡牌与机制自动换行须避免闭合/句读标点落在行首，显式换行后的用户标点保留。
- 卡牌 `text_layout=smart/wrap/off`，缺省 `smart`；`wrap` 仅自动换行/缩字号，`off` 仅显式换行、固定最大字号且不避让角标。smart 优先避免闭标点/句读位于行首及比较/运算符、前引号或开括号留在行尾，再在同字号且不增加行数时避免高亮短语跨行、内嵌图标位于行首；会增加行数则回退。其余规则与阈值见术语表，机制不支持此字段。
- 文本、数字、描边/位图、轮廓裁剪等校验与安全逻辑不属于可精简的冗余。

## WebGUI 行为

- 三个主 tab：卡牌库、对局预览、全局布局设置。布局与对局页分别由「手动调整布局」「扩展功能」控制显隐；`/layout` 仅保留到 `/#layout` 的重定向。
- 再次点击已选条目取消选择：卡牌回所属式神、式神回项目、项目/机制回到仅显示全局机制。全局机制选中时清空项目/式神/卡牌；非全局机制保留所属上下文，列表显示全局+当前项目+当前式神机制，其中非全局机制名称加粗。新建/取消全局按最近选择归属（式神优先），无项目则拒绝。
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
