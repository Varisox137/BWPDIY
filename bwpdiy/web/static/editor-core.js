// ================= 共享常量与工具 =================
const TYPES = ["式神", "战斗", "法术", "形态", "幻境", "协战"];
const FACTIONS = ["红莲", "苍叶", "青岚", "紫岩", "无相"];
const RARITIES = ["N", "R", "SR", "SSR"];
const LEVELS = [1, 2, 3], ENTITY_LEVELS = [0, 1, 2, 3];
// stat 字段口径与 store/schema.py 对齐：式神/形态 power+health、幻境 durability 非负；
// 战斗 power+/shield+、觉醒法术 power+/health+ 可负；协战无 stat
const STATS_BY_TYPE = {
  "式神": ["power", "health"], "战斗": ["power+", "shield+"], "法术": ["power+", "health+"],
  "形态": ["power", "health"], "幻境": ["durability"], "协战": [],
};
const SIGNED_STATS = ["power+", "shield+", "health+"];
// stat 适用矩阵（与 badges.py _STAT_MATRIX 同口径）：type -> {field: 输入框标签}
// 表外组合不提供输入框也不绘制；法术仅觉醒（evolve）有 stat；式神/形态/幻境强制非负
const STAT_MATRIX = {
  "式神": {"power": "力量", "health": "生命"},
  "战斗": {"power+": "力量+", "shield+": "护甲+"},
  "法术": {"power+": "力量+", "health+": "生命+"},
  "形态": {"power": "力量", "health": "生命"},
  "幻境": {"durability": "耐久"},
};
const NONNEG_TYPES = new Set(["式神", "形态", "幻境"]);
// 觉醒（evolve）仅战斗/法术/形态/幻境；式神/协战不提供勾选框（与 store schema 同口径）
const EVOLVE_TYPES = new Set(["战斗", "法术", "形态", "幻境"]);
// 框品：内部值 → 中文显示名；可携带类型 = 式神/战斗/法术/形态/幻境（式神牌框同形态；协战恒 norm 不可）
const FRAME_VARIANTS = [["norm", "常规"], ["blue", "琉璃"], ["black", "墨染"], ["red", "百炼"]];
const FRAME_VARIANT_VALUES = new Set(FRAME_VARIANTS.map(([v]) => v));
const FRAME_VARIANT_TYPES = new Set(["式神", "战斗", "法术", "形态", "幻境"]);
// 勾玉六色：内部值 → 中文显示名（缺省 yellow 不写进 yaml；素材 assets/levels/level_<n>_<color>.png）
const LEVEL_COLORS = [["yellow", "黄"], ["cyan", "青"], ["purple", "紫"],
                      ["red", "红"], ["blue", "蓝"], ["brown", "棕"]];
const LEVEL_COLOR_VALUES = new Set(LEVEL_COLORS.map(([v]) => v));
const FACTION_STYLES = [1, 2, 3];  // 派系样式（缺省 2 不写进 yaml）
// 数值变色：stat 伴随字段 <field>_color（缺省白不写进 yaml）；红=debuff/受伤、绿=buff、紫=中毒
const STAT_VALUE_COLORS = [["white", "白"], ["red", "红"], ["green", "绿"], ["purple", "紫"]];
const STAT_VALUE_COLOR_VALUES = new Set(["red", "green", "purple"]);

let layouts = null;          // 完整布局 dict（/api/layout），两 tab 共享
let samples = null;          // 六类型样卡字段（/api/samples），布局 tab 用

// 服务失联弹窗：服务连续 2h 无任何操作（HTTP 请求）会自动终止（防占用）；
// 此后一切请求连接失败——包装 fetch 统一捕获，弹一次说明（JSON 解析失败等非
// 网络错误不触发：只有 fetch 自身 reject 才是连接级失败）
let serverDownShown = false;
let manualShutdown = false;
let pendingStorageWrites = 0;
const _origFetch = window.fetch.bind(window);
function tracksStorageWrite(args) {
  const [resource, options = {}] = args;
  const method = (options.method || resource.method || 'GET').toUpperCase();
  const url = typeof resource === 'string' ? resource : resource.url;
  return ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)
    && !url.endsWith('preview') && !url.includes('/api/client-log');
}
window.fetch = (...args) => {
  const tracked = tracksStorageWrite(args);
  if (tracked) pendingStorageWrites++;
  return _origFetch(...args).catch(e => {
    if (!serverDownShown && !manualShutdown) {
      serverDownShown = true;
      document.getElementById('server-down-modal').style.display = 'block';
    }
    throw e;
  }).finally(() => { if (tracked) pendingStorageWrites--; });
};
// GUI 事件写入单次运行日志；绕过服务失联弹窗，日志失败不影响编辑操作。
function guiDebug(event, detail = '') {
  const text = typeof detail === 'string' ? detail : JSON.stringify(detail);
  _origFetch('/api/client-log', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({event, detail: text})}).catch(() => {});
}
document.addEventListener('click', ev => {
  const button = ev.target.closest('button');
  if (button) guiDebug('button.click', button.id || button.textContent.trim().slice(0, 80));
}, true);
document.addEventListener('change', ev => {
  const el = ev.target;
  if (!el.matches('input, select, textarea') || el.type === 'file') return;
  const label = el.id || (el.closest('label') ? el.closest('label').textContent.trim() : '') || el.type;
  const isText = el.tagName === 'TEXTAREA' || ['text', 'search', 'password'].includes(el.type);
  const value = el.type === 'checkbox' ? el.checked
    : (isText ? `(已修改，长度 ${el.value.length})` : el.value);
  guiDebug('field.change', `${label.replace(/\s+/g, ' ').slice(0, 80)}=${value}`);
}, true);

async function ensureLayouts() {
  if (!layouts) layouts = await (await fetch('/api/layout')).json();
  return layouts;
}
function deepCopy(o) { return JSON.parse(JSON.stringify(o)); }
function enc(s) { return encodeURIComponent(s); }
// 422 detail 三结构兼容：StoreError→字符串、SchemaError→中文错误列表、
// FastAPI body 校验→pydantic dict 列表（取 loc+msg）；统一返回消息数组
async function parseErrorDetail(r) {
  let d;
  try { d = (await r.json()).detail; } catch (e) { return ['HTTP ' + r.status]; }
  if (typeof d === 'string') return [d];
  if (Array.isArray(d)) return d.map(e => {
    if (typeof e === 'string') return e;
    if (e && e.msg) return `${(e.loc || []).join('.')}：${e.msg}`;
    return JSON.stringify(e);
  });
  return [JSON.stringify(d)];
}

// ================= 顶部 tab 导航 =================
function showTab(name) {
  document.querySelectorAll('.navtab').forEach(b =>
    b.classList.toggle('active', b.dataset.tab === name));
  document.getElementById('tab-cards').classList.toggle('active', name === 'cards');
  document.getElementById('tab-layout').classList.toggle('active', name === 'layout');
  history.replaceState(null, '', name === 'layout' ? '#layout' : '#cards');
  if (name === 'layout') {
    captureLayoutSnapshot();  // 每次进入都尝试记录快照（dirty 时跳过，保住本轮编辑前的基准）
    layoutBoot();  // 布局 tab 懒初始化（首次进入才拉取样卡/渲染预览）
  }
}
// tab 切换门卫：未保存修改弹窗提醒（不丢弃——布局/卡牌修改均保留在内存，仅提示）；
// 单卡布局模式下离开布局 tab：确认后退出单卡模式（布局调整丢弃，卡牌内容修改保留回卡牌库）
async function tryShowTab(name) {
  const cur = document.getElementById('tab-layout').classList.contains('active') ? 'layout' : 'cards';
  if (name === cur) return;
  if (cardLayoutMode) {
    if ((singleDirty || cDirty) && !await sessionConfirm(
        '单卡布局有未保存修改，离开将丢弃布局调整（卡牌内容修改保留），继续？', 'unsaved')) return;
    exitCardLayout();
    if (formData) { buildForm(); scheduleCardPreview(); }  // 模式内卡牌内容修改同步回卡牌库表单与预览
  } else if (cur === 'cards' && (cDirty || mDirty)) {
    if (!await sessionConfirm('当前卡牌/机制有未保存修改（切换栏目不会丢弃，但仍未保存），继续？', 'unsaved')) return;
  } else if (cur === 'layout' && dirty) {
    if (!await sessionConfirm('布局有未保存修改（切换栏目不会丢弃，但仍未保存），继续？', 'unsaved')) return;
  }
  showTab(name);
}
document.querySelectorAll('.navtab').forEach(b => b.onclick = () => tryShowTab(b.dataset.tab));
// 布局 navtab 文案：单卡模式下显示「单卡布局设置」
function updateLayoutNavtab() {
  document.querySelector('.navtab[data-tab="layout"]').textContent =
    cardLayoutMode ? '单卡布局设置' : '全局布局设置';
}

// ================= 顶栏扩展选项（localStorage 持久化） =================
// 标记扩展（marker）：N 稀有度 + 勾玉六色 + 式神等级 + 派系样式；取消勾选只隐藏控件，
// 已写进卡牌的数据（level_color 等）不回退、渲染照常生效
const EXT_KEY = 'bwpdiy_ext_options';
const extOptions = {layout: false, marker: false};
try { Object.assign(extOptions, JSON.parse(localStorage.getItem(EXT_KEY) || '{}')); } catch (e) {}
if (extOptions.rarity_n) { extOptions.marker = true; delete extOptions.rarity_n; }  // 旧键迁移
function saveExtOptions() { localStorage.setItem(EXT_KEY, JSON.stringify(extOptions)); }
function applyExtOptions() {
  document.getElementById('ext-layout').checked = extOptions.layout;
  document.getElementById('ext-marker').checked = extOptions.marker;
  // 不勾选「手动调整布局」时隐藏布局设置 navtab；当前正在布局 tab 则退回卡牌库
  document.querySelector('.navtab[data-tab="layout"]').style.display = extOptions.layout ? '' : 'none';
  if (!extOptions.layout) {
    if (cardLayoutMode) exitCardLayout();  // 单卡布局模式随扩展关闭退出（布局调整丢弃）
    if (document.getElementById('tab-layout').classList.contains('active')) showTab('cards');
  }
  if (formData) buildForm();  // 稀有度/勾玉颜色等下拉随扩展选项变化
}
document.getElementById('ext-layout').onchange = ev => {
  extOptions.layout = ev.target.checked; saveExtOptions(); applyExtOptions();
};
document.getElementById('ext-marker').onchange = ev => {
  extOptions.marker = ev.target.checked; saveExtOptions(); applyExtOptions();
};
// 稀有度下拉选项：默认 R/SR/SSR；勾选标记扩展或当前卡已是 N 时含 N；
// 「无」（缺省 rarity 键 = 衍生牌口径，不绘制双标）仅在标记扩展下可选，
// 当前卡无 rarity 时也保留该选项以免 select 显示空白
function rarityOptions() {
  const base = (extOptions.marker || (formData && formData.rarity === 'N'))
    ? RARITIES : RARITIES.filter(r => r !== 'N');
  return (extOptions.marker || (formData && !formData.rarity)) ? [...base, '无'] : base;
}
