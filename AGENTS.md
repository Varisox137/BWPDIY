# BWPDIY 项目级约定

《阴阳师百闻牌》DIY 卡牌工具。设计文档：`docs/superpowers/specs/20260914-bwpdiy-design.md`；术语表：`docs/terminology.md`。用户级总纲见 `C:/Users/Varis/.kimi-code/AGENTS.md`，冲突时本文件优先。

## 架构红线

- 单包分层：`bwpdiy/render`（纯 PIL 渲染库）← `bwpdiy/store`（卡牌库+校验）← `bwpdiy/web`（FastAPI 编辑器）。**render 不得 import store/web**（BWPro 只 import `bwpdiy.render`，不能拖入 FastAPI）。`bwpdiy/updater.py`（exe 自动更新：GitHub latest release 检查 + 一键下载替换重启；GUI 加载即查一次、此后每 1min 复查）仅 web 层引用。
- 预览性能（v1.7.0）：普通卡牌框后的静态绘制命令/层序列按原顺序重放，LRU 最多 8 条，不合并成单一覆盖层，须与旧管线逐像素一致；缩放卡图中间图 LRU 总像素不超过 64,000,000。鼠标预览按 art/entity/portrait 独立 `requestAnimationFrame` 调度，每通道每帧最多一次、取最新值、互不取消，art 联动主卡与实体，mouseup 强制最终预览；响应按已处理序号防逆序覆盖，连续编辑时允许显示最新已完成画面，切卡/清空仍使旧响应失效；普通输入仍用 300ms 防抖。
- 空闲自动终止（防占用）：web 层活动统计中间件 + 看门狗线程，连续 2h 无 HTTP 操作则进程退出（`/api/update/check` 与 `/api/update/progress` 自动轮询不计入活动；`create_app(idle_timeout=, on_idle=)` 可注入，≤0 关闭）；GUI 包装 fetch，连接级失败弹「连接已断开」说明窗。
- 运行日志（v1.5.2，`bwpdiy/runlog.py`）：每次启动写 `<运行目录>/logs/bwpdiy-<日期时间>.log`（exe 取 exe 目录、开发取 cwd，不可写回退临时目录 `bwpdiy-logs/`；保留最近 10 次），root=文件+控制台双 handler，uvicorn `log_config=None` 接入 root（access 降级 WARNING）；启动参数/更新全过程/未捕获异常落盘，启动时打印日志路径提示用户反馈附日志。自动更新下载带进度回报（模块级 `_PROGRESS` + `/api/update/progress`，GUI 1s 轮询显示 MB/百分比）与总时长预算 `DOWNLOAD_MAX_SECONDS=600`（低速涓流整体兜底），失败删半截文件、前端给「前往下载」手动入口。
- `legacy/` 只读封存参考（旧版半成品源码与资源，无版本控制），任何情况下不修改、不删除。
- `library/` 是用户创作数据，gitignore，不提交。
- `assets/` 美术资源来自 legacy `basics/` 与 PSD 导出（`scripts/import_psd_assets.py` 生成）：命名约定牌框 `frames/{form,combat,spell,field,reinforce}_{框品}.png`（协战仅 norm）、等级 `levels/{base,evolve_star,level_{1,2,3}_{yellow,cyan,purple,red,blue,brown}}.png`（v1.4.0 六色）、稀有度 `rarity/{R,SR,SSR}{,_blue,_red}.png`+`reinforce_*`+`N.png`、数值标 `stats/{power,health,combat_shield,combat_fragile_{1,2},field_intensity}.png`（力量/生命全类型共用，无类型前缀）、正负号 `signs/{plus,minus}.png`、协战双式神框 `duo/{frame_{1,2},back,highlight_1}.png`（v1.4.1，frame 为双框拆半；槽位2 高光由 highlight_1 旋转 180° 派生不单存；派系小标复用 `factions/`，不在 duo 目录单存；底板带半透明光晕需按 alpha≥128 可见 bbox 裁边居中，高光/框线只做 alpha>0 裁边保持层间配准）、机制描述框 `mech/{frame_invocation_{3,4,5},frame_skill_{3,4,5},frame_seal,badge_{bless,eclipse}}.png`（v1.5.0）；masks 已废弃；旧位图资产封存 `assets/legacy/`。改动须同步 `docs/terminology.md`。

## 数据纪律

- 卡牌库结构（v1.2.2）：`library/<项目>/shikigami/*.yaml`（式神卡）+ `cards/*.yaml` + `images/`（上传卡图按 `<id 或卡名><ext>` 命名，改 id 不重命名已有卡图）；文件名与卡名脱钩（卡名=文件内 name）；id 支持两位简写（v1.6.2：非协战卡有所属式神且其 id 为 6 位数字时，保存展开为 式神id+两位，协战/中立卡不展开），式神改名由 store 层联动更新同项目引用。**多版本（v1.6.0）**：卡牌/机制均有 `version_date`（YYYYMMDD，保存校验合法日期、留空由服务端填当天）；「新版本」创建的文件名 `基础stem@日期`，旧无 @ 文件不强制迁移；卡牌按 id+name 归组、机制按 name 归组，数量限制（式神 49/非式神 299）按组数计；同组共享 `layout` 与 `artwork`（同图同设置），保存任一版本同步到组内其他版本；带 @ 文件改日期会重命名。上传卡图按表单当前 id 优先命名（v1.6.2，含两位简写展开，未填回退卡名）；主要式神/卡牌衍生物列表按 id 升序（无 id 在后按名称），卡牌栏按当前主要式神筛选、可切中立牌，版本下拉常驻且可删当前版本。退出时 `cleanup_unused_images` 删除各项目 images/ 下无引用图片（缺省 <id 或卡名>.png 也算引用）：正常退出 atexit、闲置终止 on_idle 回调、一键更新 update_apply 显式调用（os._exit 绕过 atexit）。
- 卡牌 yaml 分引擎段（与 BWPro 口径对齐，按类型分字段；协战所属式神为 `shikigami1`/`shikigami2`）与渲染段（`artwork.images` 列表，全可缺省）。schema 字段只增不改。
- 描述文本（description）支持 `[[关键字]]` 高亮标记（双英文方括号、括号不绘制、按框品异色；从左往右匹配、未匹配括号按字面文本显示（v1.3.0 起不再报错）；单 [ ] 为字面字符；解析见 `render/text.py` parse_keyword_segments）与 `#xx` 内嵌图标（v1.3.0，两位拼音首字母代码见 `render/text.py` ICON_CODES，未知代码报错；派系图标墨染框用 `_black` 变体；大小=字号×desc 区 `icon_scale`，与相邻文字间自动加四分之一宽空格（0.25em），宽度计入换行与居中）。
- 机制（v1.5.0）：全局共享池 `library/mechanisms/*.yaml`（跨项目复用，不属任何项目；项目名保留字 `mechanisms`）；字段 name/frame（invocation 灵咒框/skill 关键字框/seal 加护蚀印框）/text/badge（bless/eclipse，仅 seal）；内容行数（关键字名+空行+描述行，下限 2 行）× 行距（=正文字号）决定框高、非原生行数/行距按行高横带拼接/裁除，关键字名左上角左对齐金色（字号略大于正文、不加粗）、描述逐行左对齐、badge 存在时名称右移避让、正文色按框体（render/mech.py）；渲染参数入布局配置「机制」段（字号/小图标三类共用，文本区域 frames.<框> 各框独立 text_x/text_dy/width——关键字名与描述同左缘不单独偏移；无高度：框高随内容行动态变化，GUI 绿框按 render_mechanism info 出参的实际文本块画出；角标 badge_size/badge_pos 在 frames.seal 下），GUI 布局设置第八类「机制」页三画布同屏调参（浅绿框标示文本区域）。原版游戏无「技能」概念——机制相关术语一律用「关键字」，禁用「技能」（psd_export 归档素材文件名除外）。
- 对局式神（v1.7.0）：`render/entity.py` 的 `render_entity` 独立渲染 96×144 小卡，等级 0–3（0 不绘制等级组件），式神/形态/觉醒卡在卡牌详情常驻预览与导出（式神头像左、实体右；形态/觉醒仅实体），临时状态不写回卡牌；`art_scale` 仅控制对局卡图缩放，按来源牌框最大封闭透明窗修正 y 偏移。布局配置另含「对局式神」独立段（version 2，level 与 power/health/combat_power/shield 元素及 art_window 内窗，无文本区），旧 64×96 配置一次性迁移；GUI 第七类「对局式神」页独立编辑，可拖拽内窗并调整 center/width/height/frame_center/offset_y，不加入普通六类型、不做跨类型传播、不显示觉醒星参数；布局小卡 CSS 3 倍显示；样卡力量/生命（非负）与战力/护甲（整数）可临时调整且不写盘；元素可越出 96×144 框体并按联合可见边界裁剪，鼠标按显示比例反算，PNG 保持原生尺寸。
- 机制未实现不进数据；字段/枚举变更须同步设计文档与术语表。

## 工程纪律

- 测试命令（Windows Git Bash）：`PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q`
- 依赖用 uv（`uv add` / `uv sync`），不用 pip 直装。
- 中文 conventional commit；每次 commit 后 `git push`（失败不阻塞，汇报即可）；rebase/reset/分支操作先问。
- 大改动先 plan mode；批量新功能委托子代理，收尾全量测试由主上下文亲跑。
- 发布：pyinstaller 打包 `releases/BWPDIY-v<版本>.exe`（`scripts/build_exe.py`，同时生成 `<exe>.sha256` 校验文件）+ `gh release create`（exe 与 .sha256 两个资产都要上传，客户端下载后强制校验）；本地 `releases/` 保留规则：**exe 每个二级版本（前两位）只留最新版**（三级小更新发布时删去该二级版本下的过往 GitHub release 与本地旧 exe），**sha256 上传后本地一律不留**。出厂全局布局配置（`assets/layout.json`）有变更的版本，`bwpdiy/changelog.py` 该版本首条必须加粗提示「本次更新更改了全局布局配置，用户可能需要重新手动调整本地配置」（条目按 innerHTML 渲染，支持 <b> 标签）。
