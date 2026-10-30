// ================= 布局设置 tab =================
// 自原 static/layout.html 迁入：DOM id 加 l- 前缀、入口改懒初始化 layoutBoot、
// 列表选择器限定 #l-sidebar 作用域；函数名/常量名保持原样（tests/test_web.py 的 node 抽取测试依赖）
// stat 图标由数值字段推导 stats/{stem}.png（力量/生命全类型共用），无手动选择项
const FONTS = ['name', 'desc'];
// 内部标识 → 界面中文显示名（未收录原样显示；图标码语义见 docs/terminology.md 内嵌图标段）
const DISP = {
  // 布局元素名 / 文本区名 / 字体键
  level: '等级标', faction: '派系标', rarity: '稀有度', power: '力量', health: '生命',
  shield: '护甲', durability: '耐久', name: '卡名', footer: '脚注', desc: '描述',
  duo_frame: '双式神框', art_window: '卡图内窗',
  // 元素 kind
  stat: '数值', rarity_flank: '稀有度双标', level_badge: '等级标', text: '文本',
  // stat 字段
  'power+': '力量+', 'shield+': '护甲+', 'health+': '生命+',
  // stat 图标码（资源代号）
  ll: '力量', sm: '生命', hj: '护甲', pj: '破甲', nj: '耐久', zl: '战力', fl: '乏力', nl: '能量',
};
function disp(k) { return DISP[k] || k; }
// stat 输入框从当前类型布局的 stat 元素 field 派生（不硬编码 field），再按矩阵过滤
function statInputs() {
  const allowed = STAT_MATRIX[curType] || {};
  if (curType === "法术" && !cardField('evolve')) return [];  // 非觉醒法术无 stat
  const inputs = [];
  for (const e of Object.values(typeLayout().elements)) {
    if (e.kind === 'stat' && e.field in allowed) inputs.push([e.field, allowed[e.field]]);
  }
  return inputs;
}
let cardOverrides = {};      // type -> {field: value} 卡牌内容覆盖（POST /api/preview 的 card）
let curType = "式神";
let layoutFrameVariant = "norm";  // 当前全局布局框品；单卡模式仅切换预览框品
function globalTypeLayout(t, variant = layoutFrameVariant) {
  const base = layouts && layouts[t];
  if (!base || variant === 'norm' || t === '协战') return base || null;
  return (base.frame_variants && base.frame_variants[variant]) || base;
}
function layoutForRender(layout) {
  return {elements: layout.elements, text_regions: layout.text_regions};
}
function syncLayoutFrameButtons() {
  const shown = FRAME_VARIANT_TYPES.has(curType) ? layoutFrameVariant : 'norm';
  document.querySelectorAll('#l-frame-variants .fv').forEach(b => {
    b.classList.toggle('active', b.dataset.fv === shown);
    b.disabled = entityLayoutMode || (b.dataset.fv !== 'norm' && !FRAME_VARIANT_TYPES.has(curType));
  });
}
// 框品按钮：切换同类型的独立布局；未保存工作保留在对应框品工作副本中
document.querySelectorAll('#l-frame-variants .fv').forEach(b => b.onclick = async () => {
  if (b.disabled || b.dataset.fv === layoutFrameVariant) return;
  if ((cardLayoutMode ? singleDirty : dirty) &&
      !await sessionConfirm('布局有未保存修改（切换框品不会丢弃，但仍未保存），继续？', 'unsaved')) return;
  layoutFrameVariant = b.dataset.fv;
  selectType(curType);
});
let sel = null;              // {kind:'element'|'region', name}
let dirty = false;
let layoutSnapshot = null;   // 本轮布局编辑前的已保存快照（「还原」基准；dirty 时不再覆写）
// ---- 单卡布局模式：从卡牌库「调整单卡元素布局」进入，编辑当前卡的 layout 覆盖段 ----
// 工作副本 singleLayout = 该卡类型全局布局 深合并 卡面 layout 段；保存时剔同写稀疏覆盖
let cardLayoutMode = null;   // null | 当前卡 stem
let singleLayout = null;     // 合并后的单类型布局工作副本（typeLayout() 在模式内返回它）
let singleSnapshot = null;   // 进入模式时的快照（「还原更改」基准）
let singleDirty = false;
// ---- 机制布局模式：布局 tab 第八类「机制」，三画布同屏预览三类框体（仅全局模式可进）----
let mechLayoutMode = false;
// 对局式神是独立全局布局段，不属于六种卡牌类型，也与卡牌库临时预览模式分离。
let entityLayoutMode = false;
// 布局样卡数值仅控制预览，不写盘、不计入未保存。
const entityLayoutSample = {level: 2, level_color: 'yellow',
  power: 2, health: 5, combat_power: 1, shield: -1};
// 与 render/mech.py DEFAULT_LAYOUT 同口径（缺键/缺段时补齐，保存时全段随 layouts 写回）：
// 三类框共用仅字号/小图标；角标配置随 seal 区域（badge 仅 seal 合法）；名称无独立偏移
const MECH_LAYOUT_DEFAULTS = {name_size: 26, text_size: 24, icon_scale: 1.0};
// 各框独立文本区域缺省（区域无固定高度：框高随内容行数动态变化，
// 绿框按服务端返回的实际文本块矩形画出）；seal 区域附加角标尺寸/坐标
const MECH_REGION_DEFAULT = f => f === 'seal'
  ? {text_x: 18, text_dy: 0, width: 288, badge_size: 30, badge_pos: [6, 6]}
  : {text_x: 18, text_dy: 0, width: 288};
const MECH_FRAME_LABELS = {invocation: '灵咒框', skill: '关键字框', seal: '加护蚀印框'};
// 机制预览示例内容（仅调布局用，不写盘、不计入未保存）
const mechSample = {name: '示例机制',
  text: '[[唯一]]。\n己方回合开始时，获得1#ll和[[贯通]]。\n攻击后移除。', badge: false};
function mechLayout() {
  const m = layouts['机制'] = layouts['机制'] || {};
  // 开发期旧键（共用基础偏移/叠加偏移/双边距/顶层角标与名称偏移）已废弃，直接删除不回迁
  for (const k of ['name_x', 'name_dy', 'text_x', 'text_y', 'margin_x', 'frame_offset',
                   'badge_size', 'badge_pos', 'name_offset'])
    delete m[k];
  for (const [k, v] of Object.entries(MECH_LAYOUT_DEFAULTS))
    if (m[k] === undefined) m[k] = deepCopy(v);
  m.frames = (m.frames && typeof m.frames === 'object' && !Array.isArray(m.frames))
    ? m.frames : {};
  for (const f of Object.keys(MECH_FRAME_LABELS)) {
    const rg = m.frames[f] =
      (m.frames[f] && typeof m.frames[f] === 'object' && !Array.isArray(m.frames[f]))
        ? m.frames[f] : {};
    delete rg.height;  // 开发期旧键（区域固定高）已废弃：绿框按实际文本块画出
    for (const [k, v] of Object.entries(MECH_REGION_DEFAULT(f))) {
      if (Array.isArray(v)) {  // 坐标对（badge_pos）
        if (!Array.isArray(rg[k]) || rg[k].length !== 2 ||
            !rg[k].every(Number.isFinite)) rg[k] = [...v];
      } else if (!Number.isFinite(rg[k])) rg[k] = v;
    }
  }
  return m;
}
const canvas = document.getElementById('l-preview');
const ctx = canvas.getContext('2d');
const statusEl = document.getElementById('l-status');
let previewImg = null;     // 预览图（紧致裁剪原尺寸；布局坐标为卡面空间，按 previewOffset 换算）
let previewOffset = [0, 0];  // 裁剪原点（X-Crop-Offset 响应头，卡面空间），覆盖层/鼠标据此换算

// 懒初始化：首次进入布局 tab 才拉取布局/样卡并渲染（卡牌库 tab 不白付预览开销）
let layoutInited = false;
async function layoutBoot() {
  if (layoutInited) return;
  layoutInited = true;
  try {
    await ensureLayouts();
    samples = await (await fetch('/api/samples')).json();
    captureLayoutSnapshot();  // 首次进入：showTab 时 layouts 尚未拉取，加载成功后补记快照
  } catch (e) {
    layoutInited = false;
    statusEl.textContent = '布局加载失败: ' + e;
    return;
  }
  buildTypes(); selectType(cardLayoutMode ? curType : '式神');  // 默认卡牌类型：式神（单卡模式保持该卡类型）
}
function typeLayout() {
  if (entityLayoutMode) return layouts['对局式神'];
  return cardLayoutMode ? singleLayout : globalTypeLayout(curType);
}
function layoutRegions() {
  const layout = typeLayout();
  return entityLayoutMode ? {art_window: layout.art_window} : (layout.text_regions || {});
}
function markDirty() { if (cardLayoutMode) singleDirty = true; else dirty = true; }
// 快照记录：仅在无未保存修改时覆写，保证快照恒为本轮编辑前的已保存状态
function captureLayoutSnapshot() {
  if (layouts && !dirty) layoutSnapshot = deepCopy(layouts);
}
// 递归差异比较：返回「元素名.键路径」列表（如 elements.name.pos）；键缺失或值不同均计为一处
function layoutDiffs(a, b) {
  const out = [];
  const walk = (x, y, p) => {
    const isObj = v => v !== null && typeof v === 'object' && !Array.isArray(v);
    if (isObj(x) && isObj(y)) {
      for (const k of new Set([...Object.keys(x), ...Object.keys(y)])) {
        const kp = p ? p + '.' + k : k;
        if (!(k in x) || !(k in y)) out.push(kp);
        else walk(x[k], y[k], kp);
      }
    } else if (JSON.stringify(x) !== JSON.stringify(y)) out.push(p);
  };
  walk(a, b, '');
  return out;
}
// 差异列表展示：最多列前 10 条，超出截断为「…等 N 处」
function formatDiffs(diffs) {
  const shown = diffs.slice(0, 10).join('、');
  return diffs.length > 10 ? `${shown} 等 ${diffs.length} 处` : shown;
}
// 还原：all=false 仅还原当前独立布局段，true 还原六类型+对局式神+机制；
// 还原本身计入未保存修改（markDirty）
function restoreLayout(all) {
  if (!layoutSnapshot) { statusEl.textContent = '布局尚未加载'; return; }
  const current = entityLayoutMode ? '对局式神' : (mechLayoutMode ? '机制' : curType);
  const targets = all ? [...TYPES, '对局式神', '机制'] : [current];
  const parts = [];
  for (const t of targets) {
    const d = layoutDiffs(layouts[t] || {}, layoutSnapshot[t] || {});
    if (d.length) parts.push(`${t}：${formatDiffs(d)}`);
  }
  if (!parts.length) { statusEl.textContent = '无更改可还原'; return; }
  if (!confirm('将还原以下布局更改：\n' + parts.join('\n'))) return;
  for (const t of targets) {
    if (t in layoutSnapshot) layouts[t] = deepCopy(layoutSnapshot[t]);
  }
  markDirty();
  if (entityLayoutMode) selectEntityLayout();
  else if (mechLayoutMode) selectMechLayout();
  else selectType(curType);  // 全套重建并刷新预览
  statusEl.textContent = '已还原（未保存）';
}
// 当前类型卡牌内容：样卡字段 + 用户覆盖（覆盖优先；不改的不传，后端深拷贝合并）；
// 单卡模式直接读写真实卡牌 formData（内容修改随「保存并返回」写盘）
function cardField(name) {
  if (cardLayoutMode) return formData[name];
  const ov = cardOverrides[curType] || {};
  return name in ov ? ov[name] : (samples[curType] || {})[name];
}
function setCardField(name, value) {
  if (cardLayoutMode) {
    if (value === null || value === undefined) delete formData[name];
    else formData[name] = value;
    cDirty = true;  // 卡牌内容修改：回卡牌库后保持未保存标记
  } else {
    (cardOverrides[curType] = cardOverrides[curType] || {})[name] = value;
  }
  schedulePreview();
}

// 实时预览：任何调整后防抖 300ms 自动刷新（拖拽 mousemove 不走这里，mouseup 直接刷）
let previewTimer = null;
let previewSeq = 0;  // 请求序号：旧响应到达时丢弃，避免乱序覆盖新图
function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(refreshPreview, 300);
}

// 类型 tab（单卡模式：替换为大标题 + 单个「还原更改」按钮）
function buildTypes() {
  const div = document.getElementById('l-types');
  div.innerHTML = '';
  if (cardLayoutMode) {
    const h = document.createElement('h3');
    h.textContent = `手动调整单卡：${curType}`;
    h.style.margin = '4px 0';
    div.appendChild(h);
    const b = document.createElement('button');
    b.textContent = '还原更改';
    b.onclick = restoreSingleLayout;
    div.appendChild(b);
    return;
  }
  for (const t of TYPES) {
    const b = document.createElement('button');
    b.textContent = t; b.className = 'tab';
    b.onclick = async () => {
      // 切换类型不丢弃修改（layouts 常驻内存），但提醒仍未保存
      if ((t !== curType || mechLayoutMode || entityLayoutMode) && dirty &&
          !await sessionConfirm('布局有未保存修改（切换类型不会丢弃，但仍未保存），继续？', 'unsaved')) return;
      selectType(t);
    };
    div.appendChild(b);
  }
  const be = document.createElement('button');
  be.textContent = '对局式神'; be.className = 'tab';
  be.onclick = async () => {
    if (!entityLayoutMode && dirty &&
        !await sessionConfirm('布局有未保存修改（切换类型不会丢弃，但仍未保存），继续？', 'unsaved')) return;
    selectEntityLayout();
  };
  div.appendChild(be);
  // 第八类「机制」：机制描述框布局（三画布同屏预览三类框体，配置三类共用）
  const bm = document.createElement('button');
  bm.textContent = '机制'; bm.className = 'tab';
  bm.onclick = async () => {
    if (!mechLayoutMode && dirty &&
        !await sessionConfirm('布局有未保存修改（切换类型不会丢弃，但仍未保存），继续？', 'unsaved')) return;
    selectMechLayout();
  };
  div.appendChild(bm);
  // 还原按钮：无 .tab class，不参与 selectType 的 active 切换
  const row = document.createElement('div');
  row.className = 'btnrow';
  const bAll = document.createElement('button');
  bAll.textContent = '还原所有更改';
  bAll.onclick = () => restoreLayout(true);
  const bCur = document.createElement('button');
  bCur.textContent = '还原当前类型更改';
  bCur.onclick = () => restoreLayout(false);
  row.appendChild(bAll);
  row.appendChild(bCur);
  div.appendChild(row);
}
// 单卡模式「还原更改」：还原到进入模式时的快照（弹窗列出差异；还原本身计入未保存）
function restoreSingleLayout() {
  const d = layoutDiffs(singleLayout || {}, singleSnapshot || {});
  if (!d.length) { statusEl.textContent = '无更改可还原'; return; }
  if (!confirm('将还原以下单卡布局更改：\n' + formatDiffs(d))) return;
  singleLayout = deepCopy(singleSnapshot);
  singleDirty = true;
  selectType(curType);  // 全套重建（列表/属性/卡牌内容）并刷新预览
  statusEl.textContent = '已还原（未保存）';
}
function selectType(t) {
  entityLayoutMode = false; mechLayoutMode = false; showMechPanel(false);
  curType = t; sel = null; previewImg = null;  // 清旧图，避免与新类型覆盖层短暂共存
  document.querySelectorAll('#l-types .tab').forEach(b =>
    b.classList.toggle('active', b.textContent === t));
  syncLayoutFrameButtons();
  buildLists(); buildCardProps(); buildProps(); refreshPreview();
}
function selectEntityLayout() {
  entityLayoutMode = true; mechLayoutMode = false; sel = null; previewImg = null;
  document.querySelectorAll('#l-types .tab').forEach(b =>
    b.classList.toggle('active', b.textContent === '对局式神'));
  showMechPanel(false);
  syncLayoutFrameButtons();
  buildLists(); buildCardProps(); buildProps(); refreshPreview();
}

// ---- 机制布局模式：切换显隐 / 属性面板 / 三画布预览 ----
function showMechPanel(on) {
  document.getElementById('l-mech').style.display = on ? 'flex' : 'none';
  canvas.style.display = on ? 'none' : '';
  document.getElementById('l-frame-variants').style.display = on ? 'none' : '';
  for (const id of ['l-h-cardprops', 'l-cardprops', 'l-h-elems', 'l-elems'])
    document.getElementById(id).style.display = on ? 'none' : '';
}
function selectMechLayout() {
  entityLayoutMode = false; mechLayoutMode = true; sel = null; previewImg = null;
  document.querySelectorAll('#l-types .tab').forEach(b =>
    b.classList.toggle('active', b.textContent === '机制'));
  showMechPanel(true);
  buildMechProps(); refreshPreview();
}
function buildMechProps() {
  const div = document.getElementById('l-props');
  div.innerHTML = '';
  const ml = mechLayout();
  div.appendChild(title('通用设置'));
  numRow(div, '名称字号', ml.name_size, v => ml.name_size = v);
  numRow(div, '正文字号', ml.text_size, v => ml.text_size = v);
  floatRow(div, '小图标相对文字大小', ml.icon_scale, v => ml.icon_scale = v);
  // 文本区域完全分框独立（无共用基础偏移；无区域高——绿框按实际文本块画出）；
  // seal 栏按 勾选框 → 角标 → 文本区域 排列（角标配置仅 seal 合法）
  for (const [f, label] of Object.entries(MECH_FRAME_LABELS)) {
    const rg = ml.frames[f];
    div.appendChild(title(label));
    if (f === 'seal') {
      // 加护/蚀印图标预览开关（不入布局、不计未保存；
      // 启用时机制名称文本自动向右避让——实际加护/蚀印在机制编辑中逐个选择）
      const bl = document.createElement('label');
      bl.textContent = '加护/蚀印图标 ';
      const bc = document.createElement('input');
      bc.type = 'checkbox'; bc.checked = mechSample.badge;
      bc.onchange = () => { mechSample.badge = bc.checked; schedulePreview(); };
      bl.appendChild(bc); div.appendChild(bl);
      numRow(div, '角标尺寸', rg.badge_size, v => rg.badge_size = v);
      numRow(div, '角标偏移 x', rg.badge_pos[0], v => rg.badge_pos[0] = v);
      numRow(div, '角标偏移 y', rg.badge_pos[1], v => rg.badge_pos[1] = v);
    }
    numRow(div, '文本偏移 x', rg.text_x, v => rg.text_x = v);
    numRow(div, '文本偏移 y', rg.text_dy, v => rg.text_dy = v);
    numRow(div, '文本区域宽', rg.width, v => rg.width = v);
  }
  div.appendChild(title('示例内容（不保存）'));
  textRow(div, '机制名', mechSample.name, v => { mechSample.name = v; schedulePreview(); });
  const l = document.createElement('label');
  l.textContent = '描述 ';
  const ta = document.createElement('textarea');
  ta.value = mechSample.text;
  ta.onchange = () => {
    ta.value = ta.value.replace(/\n+/g, '\n').replace(/^\n|\n$/g, '');  // 连续换行合并为一个
    mechSample.text = ta.value; schedulePreview();
  };
  l.appendChild(ta); div.appendChild(l);
}
async function refreshMechPreview() {
  const seq = ++previewSeq;
  const layout = deepCopy(mechLayout());
  let err = null;
  await Promise.all(Object.keys(MECH_FRAME_LABELS).map(async frame => {
    const mech = {name: mechSample.name || '示例机制', text: mechSample.text};
    if (frame === 'seal' && mechSample.badge) mech.badge = 'bless';  // 预览统一用加护标
    let r;
    try {
      r = await fetch('/api/mech-preview', {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({frame, mechanism: mech, layout})});
    } catch (e) { err = '预览请求失败: ' + e; return; }
    if (seq !== previewSeq) return;
    if (!r.ok) { err = '预览失败: ' + (await r.json()).detail; return; }
    // 实际文本块矩形（裁剪后坐标系）随响应头返回，据以画浅绿区域轮廓
    const rect = (r.headers.get('X-Text-Rect') || '').split(',').map(Number);
    const url = URL.createObjectURL(await r.blob());
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      if (seq !== previewSeq) return;
      const cv = document.getElementById('l-mech-' + frame);
      cv.width = img.naturalWidth; cv.height = img.naturalHeight;
      const c2 = cv.getContext('2d');
      c2.drawImage(img, 0, 0);
      // 文本区域轮廓（仿卡牌布局页浅绿框）：按服务端响应头的实际文本块矩形画出
      if (rect.length === 4 && rect.every(Number.isFinite)) {
        c2.strokeStyle = '#4f4';
        c2.strokeRect(rect[0] + 0.5, rect[1] + 0.5, rect[2], rect[3]);
      }
    };
    img.src = url;
  }));
  if (seq !== previewSeq) return;
  statusEl.textContent = err || (dirty ? '● 未保存' : '');
}

// 卡牌内容输入（预览数据可编辑；改动走防抖实时预览，不涉及布局保存）
// 顺序固定：卡名 / 等级（0=无等级）/ 觉醒 / 所属式神 / 子类型 / 左下右下数值 / 文本描述
function buildCardProps() {
  const div = document.getElementById('l-cardprops');
  div.innerHTML = '';
  if (entityLayoutMode) {
    for (const [field, label, nonneg] of [
      ['power', '力量', true], ['health', '生命', true],
      ['combat_power', '战力', false], ['shield', '护甲', false],
    ]) {
      numRowC(div, label, entityLayoutSample[field], nonneg, v => {
        entityLayoutSample[field] = v;
        schedulePreview();
      }, null, 999999999999);
    }
    return;
  }
  if (!cardLayoutMode && (!samples || !samples[curType])) return;  // 单卡模式数据源是 formData，无需样卡
  textRow(div, '卡名', cardField('name') || '', v => setCardField('name', v));
  selRow(div, '等级', ['0', '1', '2', '3'], String(cardField('level') ?? 0),
    v => setCardField('level', v === '0' ? null : parseInt(v, 10)));
  if (EVOLVE_TYPES.has(curType)) {
    const l = document.createElement('label');
    l.textContent = '觉醒 ';
    const i = document.createElement('input');
    i.type = 'checkbox'; i.checked = !!cardField('evolve');
    i.onchange = () => { setCardField('evolve', i.checked); buildCardProps(); };  // 法术 stat 输入随觉醒显隐
    l.appendChild(i); div.appendChild(l);
  }
  if (curType === '协战') {  // 双式神框预览开关（单卡模式写入真实卡；样卡无 _duo 注入：勾选后渲染空槽位框）
    const l = document.createElement('label');
    l.textContent = '双式神框 ';
    const i = document.createElement('input');
    i.type = 'checkbox'; i.checked = !!cardField('duo_frame');
    i.onchange = () => setCardField('duo_frame', i.checked ? true : null);  // 关闭即删键（保持 yaml 最小化）
    l.appendChild(i); div.appendChild(l);
  }
  if ('shikigami' in samples[curType]) {
    textRow(div, '所属式神', cardField('shikigami') || '', v => setCardField('shikigami', v));
  }
  textRow(div, '子类型', cardField('special_type') || '', v => setCardField('special_type', v));
  const nonneg = NONNEG_TYPES.has(curType);  // 式神/形态/幻境 stat 强制非负
  for (const [field, label] of statInputs()) {
    const l = document.createElement('label');
    l.textContent = label + ' ';
    const i = document.createElement('input');
    i.type = 'number'; i.value = cardField(field) ?? 0;
    if (nonneg) i.min = 0;
    const commit = () => {
      let v = parseInt(i.value, 10);
      if (isNaN(v)) { i.value = cardField(field) ?? 0; return; }
      if (nonneg) v = Math.max(0, v);
      i.value = v; setCardField(field, v);
    };
    i.onchange = commit;
    i.onwheel = ev => {  // 滚轮微调
      ev.preventDefault();
      i.value = (parseInt(i.value, 10) || 0) + (ev.deltaY < 0 ? 1 : -1);
      commit();
    };
    l.appendChild(i); div.appendChild(l);
  }
  const l = document.createElement('label');
  l.textContent = '描述 ';
  const ta = document.createElement('textarea');
  ta.value = cardField('description') || '';
  ta.onchange = () => {
    ta.value = ta.value.replace(/\n+/g, '\n').replace(/^\n|\n$/g, '');  // 连续换行合并为一个
    setCardField('description', ta.value);
  };
  l.appendChild(ta); div.appendChild(l);
}
function textRow(div, label, val, set) {
  const l = document.createElement('label');
  l.textContent = label + ' ';
  const i = document.createElement('input');
  i.type = 'text'; i.value = val;
  i.onchange = () => set(i.value);
  l.appendChild(i); div.appendChild(l);
}

// 左栏列表（显示中文名，内部键存 dataset.key 供选中高亮比对）
// 元素与文本区合并为一列，固定顺序：等级 / 卡名 / 稀有度 / 描述 / 左下角组件 / 右下角组件 / 脚注
// （左右下角组件 = stat 元素按 pos.x 升序；幻境仅右下角一个）
function buildLists() {
  const tl = typeLayout();
  const ed = document.getElementById('l-elems'); ed.innerHTML = '';
  const items = [];
  for (const n of ['level', 'duo_frame', 'name', 'rarity']) {
    if (tl.elements[n]) items.push({kind: 'element', name: n});
  }
  const regions = layoutRegions();
  if (regions.desc) items.push({kind: 'region', name: 'desc'});
  if (regions.art_window) items.push({kind: 'region', name: 'art_window'});
  const stats = entityLayoutMode
    ? ['power', 'health', 'combat_power', 'shield'].filter(n => tl.elements[n])
    : Object.entries(tl.elements)
      .filter(([, e]) => e.kind === 'stat')
      .sort((a, b) => a[1].pos[0] - b[1].pos[0])
      .map(([n]) => n);
  for (const n of stats) items.push({kind: 'element', name: n});
  if (tl.elements.footer) items.push({kind: 'element', name: 'footer'});
  const listed = new Set(items.map(i => i.name));
  for (const n of Object.keys(tl.elements)) {  // 兜底：未列到的元素附加在后
    if (!listed.has(n)) items.push({kind: 'element', name: n});
  }
  for (const it of items) {
    const d = document.createElement('div');
    d.textContent = entityLayoutMode
      ? ({level: '等级', combat_power: '战力'}[it.name] || disp(it.name)) : disp(it.name);
    d.className = 'item'; d.dataset.key = it.name;
    d.onclick = () => { sel = it; refreshSel(); };
    ed.appendChild(d);
  }
}
function refreshSel() {
  document.querySelectorAll('#l-sidebar .item').forEach(d =>
    d.classList.toggle('active', sel && d.dataset.key === sel.name));
  buildProps(); draw();
}

// 预览
async function refreshPreview() {
  if (entityLayoutMode) return refreshEntityLayoutPreview();
  if (mechLayoutMode) return refreshMechPreview();  // 机制模式：三画布分通道刷新
  const seq = ++previewSeq;
  let r;
  try {
    if (cardLayoutMode) {
      // 单卡模式：项目卡预览（卡图/协战头像取项目数据），布局传工作副本；
      // 卡面 layout 键摘除（布局以显式 layout 为准，避免与服务端自动合并重复）
      const cardOv = deepCopy(formData);
      delete cardOv.layout;
      if (FRAME_VARIANT_TYPES.has(curType)) cardOv.frame_variant = layoutFrameVariant;
      r = await fetch(`/api/projects/${enc(curProject)}/cards/${enc(cardLayoutMode)}/preview`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({layout: layoutForRender(singleLayout), card: cardOv}),
      });
    } else {
      const body = {type: curType, layout: layoutForRender(typeLayout())};
      const cardOv = deepCopy(cardOverrides[curType] || {});
      if (FRAME_VARIANT_TYPES.has(curType)) cardOv.frame_variant = layoutFrameVariant;
      if (Object.keys(cardOv).length) body.card = cardOv;
      r = await fetch('/api/preview', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      });
    }
  } catch (e) {
    if (seq !== previewSeq) return;  // 过期请求的失败文案不得覆盖新状态
    statusEl.textContent = '预览请求失败: ' + e;
    return;
  }
  return handleLayoutPreviewResponse(r, seq);
}
async function refreshEntityLayoutPreview() {
  const seq = ++previewSeq;
  let r;
  try {
    r = await fetch('/api/entity-preview', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        card: {type: '式神', name: '布局样卡'},
        state: entityLayoutSample,
        layout: typeLayout(),
      }),
    });
  } catch (e) {
    if (seq === previewSeq) statusEl.textContent = '预览请求失败: ' + e;
    return;
  }
  return handleLayoutPreviewResponse(r, seq);
}
async function handleLayoutPreviewResponse(r, seq) {
  if (seq !== previewSeq) return;  // 期间又有新调整，丢弃本次结果
  if (!r.ok) {
    const detail = (await r.json()).detail;
    if (seq !== previewSeq) return;
    statusEl.textContent = '预览失败: ' + detail;
    return;
  }
  // 紧致裁剪图 + 裁剪原点（卡面空间）：画布按图尺寸，覆盖层/鼠标按原点换算
  const off = (r.headers.get('X-Crop-Offset') || '').split(',').map(Number);
  const blob = await r.blob();
  if (seq !== previewSeq) return;
  const img = new Image();
  img.onload = () => {
    if (seq !== previewSeq) { URL.revokeObjectURL(img.src); return; }
    statusEl.textContent = (cardLayoutMode ? singleDirty : dirty) ? '● 未保存' : '';
    previewOffset = (off.length === 2 && off.every(Number.isFinite)) ? off : [0, 0];
    canvas.width = img.naturalWidth; canvas.height = img.naturalHeight;
    const scale = entityLayoutMode ? 3 : 1;
    canvas.style.width = scale === 1 ? '' : `${img.naturalWidth * scale}px`;
    canvas.style.height = scale === 1 ? '' : `${img.naturalHeight * scale}px`;
    previewImg = img; draw(); URL.revokeObjectURL(img.src);
  };
  img.src = URL.createObjectURL(blob);
}

// 画布绘制：预览图为紧致裁剪原尺寸（无 512 画布留白）；布局坐标为卡面空间，
// 覆盖层整体平移 -previewOffset 换算（裁剪框内容驱动，不可作为坐标基准）
function draw() {
  if (mechLayoutMode) return;  // 机制模式无卡图画布与覆盖层
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (previewImg) ctx.drawImage(previewImg, 0, 0);
  ctx.save();
  ctx.translate(-previewOffset[0], -previewOffset[1]);
  const tl = typeLayout();
  for (const [name, e] of Object.entries(tl.elements)) {
    // 元素位置点：绿色小圆点（比文本区中心方块略小），选中变黄
    handle(e.pos, sel && sel.name === name ? '#ff4' : '#4f4', 4);
    if (e.kind === 'stat') {
      const np = [e.pos[0] + e.num_offset[0], e.pos[1] + e.num_offset[1]];
      handle(np, sel && sel.name === name ? '#ff4' : '#f8f', 5, true);
    }
    if (e.kind === 'duo_frame') {
      // 双式神框：pos=上框底图中心；下框绿点（x 恒同上框）、内框青点（上下各自偏移）、
      // 派系标粉方块（偏移上下共通，两点同显同改）
      const dy = e.slot2_dy ?? 74;
      const centers = [e.pos, [e.pos[0], e.pos[1] + dy]];
      const active = sel && sel.name === name;
      const fo1 = e.frame_offset || [0, 0];
      const fos = [fo1, e.frame_offset_2 || fo1];
      const fao = e.faction_offset || [6, 31];
      centers.forEach((c, i) => {
        handle([c[0] + fos[i][0], c[1] + fos[i][1]], active ? '#ff4' : '#4df', 4);
        handle([c[0] + fao[0], c[1] + fao[1]], active ? '#ff4' : '#f8f', 5, true);
      });
      handle(centers[1], active ? '#ff4' : '#4f4', 4);
    }
  }
  for (const [name, r] of Object.entries(layoutRegions())) {
    const active = sel && sel.name === name;
    ctx.strokeStyle = active ? '#ff4' : '#4f4';
    ctx.strokeRect(r.center[0] - r.width / 2, r.center[1] - r.height / 2, r.width, r.height);
    handle(r.center, active ? '#ff4' : '#4f4', 6);
    if (name === 'art_window') continue;
    // 文本框居中锚点（center + center_offset）：稍小的橙点后画、压在绿点之上
    const off = r.center_offset || [0, 0];
    handle([r.center[0] + off[0], r.center[1] + off[1]], '#f80', 4);
  }
  ctx.restore();
}
function handle([x, y], color, s = 6, square = false) {
  ctx.fillStyle = color;
  if (square) ctx.fillRect(x - s / 2, y - s / 2, s, s);
  else { ctx.beginPath(); ctx.arc(x, y, s, 0, 7); ctx.fill(); }
}

// 拖拽（mouseup/mousemove 挂 window，拖出画布不丢）
let drag = null;
canvas.addEventListener('mousedown', ev => {
  const [mx, my] = mousePos(ev);
  drag = pick(mx, my);
  if (drag) { sel = drag.sel; refreshSel(); }
});
window.addEventListener('mousemove', ev => {
  if (!drag) return;
  const [mx, my] = mousePos(ev);
  // 卡面空间 x 可为负（探出框左缘的元素：stat 角标/双式神框等），y 恒 0..511
  drag.set(clamp(mx, -256, 640), clamp(my, 0, 511));
  markDirty(); buildProps(); draw();
});
window.addEventListener('mouseup', () => { if (drag) { drag = null; refreshPreview(); } });
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, Math.round(v))); }
function mousePos(ev) {
  // 显示像素先按画布实际缩放比反算为原生像素，再加回裁剪原点。
  const r = canvas.getBoundingClientRect();
  return [
    (ev.clientX - r.left) * canvas.width / r.width + previewOffset[0],
    (ev.clientY - r.top) * canvas.height / r.height + previewOffset[1],
  ];
}
function pick(mx, my) {
  const tl = typeLayout();
  const near = (x, y) => Math.hypot(mx - x, my - y) < 8;
  for (const [name, e] of Object.entries(tl.elements)) {
    if (e.kind === 'stat') {
      const np = [e.pos[0] + e.num_offset[0], e.pos[1] + e.num_offset[1]];
      if (near(...np)) return { sel: {kind: 'element', name},
        set: (x, y) => { e.num_offset = [x - e.pos[0], y - e.pos[1]]; } };
    }
    if (e.kind === 'duo_frame') {
      // 双式神框拖拽点（仅协战有该元素）：
      // 派系标偏移上下共通（拖任一槽位的点改共享偏移）；内框偏移上下各自；
      // 下框底图竖直对齐（只改 dy）
      const dy = e.slot2_dy ?? 74;
      const centers = [e.pos, [e.pos[0], e.pos[1] + dy]];
      const fao = e.faction_offset || [6, 31];
      const fo1 = e.frame_offset || [0, 0];
      const fos = [fo1, e.frame_offset_2 || fo1];
      for (let i = 0; i < centers.length; i++) {
        const c = centers[i];
        if (near(c[0] + fao[0], c[1] + fao[1]))
          return { sel: {kind: 'element', name}, set: (x, y) => {
            e.faction_offset = [x - c[0], y - c[1]]; } };
        if (near(c[0] + fos[i][0], c[1] + fos[i][1]))
          return { sel: {kind: 'element', name}, set: (x, y) => {
            const off = [x - c[0], y - c[1]];
            if (i === 0) e.frame_offset = off; else e.frame_offset_2 = off; } };
      }
      if (near(...centers[1])) return { sel: {kind: 'element', name},
        set: (x, y) => { e.slot2_dy = y - e.pos[1]; } };
    }
    if (near(...e.pos)) return { sel: {kind: 'element', name}, set: (x, y) => { e.pos = [x, y]; } };
  }
  for (const [name, r] of Object.entries(layoutRegions())) {
    if (name === 'art_window') {
      if (near(...r.center)) return {sel: {kind: 'region', name},
        set: (x, y) => { r.center = [x, y]; }};
      continue;
    }
    const off = r.center_offset || [0, 0];
    // 居中锚点仅在偏移非零时可拖（与中心重合时让位给中心拖拽）
    if ((off[0] || off[1]) && near(r.center[0] + off[0], r.center[1] + off[1]))
      return { sel: {kind: 'region', name},
        set: (x, y) => { r.center_offset = [x - r.center[0], y - r.center[1]]; } };
    if (near(...r.center)) return { sel: {kind: 'region', name},
      set: (x, y) => { r.center = [x, y]; } };
  }
  return null;
}

// 右栏属性面板（标签全中文；disp 映射内部标识）
function buildProps() {
  const div = document.getElementById('l-props');
  div.innerHTML = '';
  if (!sel) { div.textContent = '点击元素/文本区以编辑'; return; }
  const tl = typeLayout();
  if (sel.kind === 'element') {
    const e = tl.elements[sel.name];
    div.appendChild(title(e.kind === 'stat'
      ? `${disp(sel.name)}（数值：${disp(e.field)}）`
      : `${disp(sel.name)}（${disp(e.kind)}）`));
    numRow(div, '位置 x', e.pos[0], v => { e.pos[0] = v; draw(); });
    numRow(div, '位置 y', e.pos[1], v => { e.pos[1] = v; draw(); });
    if (e.kind === 'stat') {
      numRow(div, '图标尺寸', e.icon_size, v => e.icon_size = v);
      numRow(div, '数字偏移 x', e.num_offset[0], v => { e.num_offset[0] = v; draw(); });
      numRow(div, '数字偏移 y', e.num_offset[1], v => { e.num_offset[1] = v; draw(); });
      numRow(div, '字号', e.font_size, v => e.font_size = v);
      // 图标由数值字段自动推导 stats/{stem}.png（力量/生命全类型共用；负护甲换破甲），不提供手动选择
      const n = document.createElement('div');
      n.className = 'note';
      n.textContent = '图标按类型与数值字段自动选择（负护甲换破甲）';
      div.appendChild(n);
      if (SIGNED_STATS.includes(e.field)) {
        // 符号类控件仅四类带符号数值（战斗 力量/护甲、法术觉醒 力量/生命）提供；
        // 式神/形态/幻境无符号，不显示符号偏移/加减号尺寸/整体偏移编辑项
        e.sign_offset ??= [0, 0];
        numRow(div, '符号偏移 x', e.sign_offset[0], v => { e.sign_offset[0] = v; draw(); });
        numRow(div, '符号偏移 y', e.sign_offset[1], v => { e.sign_offset[1] = v; draw(); });
        numRow(div, '加号尺寸', e.sign_size_plus ?? e.sign_size ?? Math.round(e.font_size * 0.5), v => e.sign_size_plus = v);
        numRow(div, '减号尺寸', e.sign_size_minus ?? e.sign_size ?? Math.round(e.font_size * 0.5), v => e.sign_size_minus = v);
        e.group_offset ??= [0, 0];
        numRow(div, '符号数字整体偏移 x', e.group_offset[0], v => { e.group_offset[0] = v; draw(); });
        numRow(div, '符号数字整体偏移 y', e.group_offset[1], v => { e.group_offset[1] = v; draw(); });
      }
      numRow(div, '描边宽度', e.stroke_width ?? 2, v => e.stroke_width = v);
      if (curType === '战斗' && e.field === 'shield+') {
        div.appendChild(title('破甲（负护甲）'));
        selRow(div, '破甲样式', ['1', '2'], String(e.fragile_variant ?? 2),
          v => e.fragile_variant = parseInt(v, 10));
        e.fragile_pos ??= [...e.pos];
        numRow(div, '破甲位置 x', e.fragile_pos[0], v => { e.fragile_pos[0] = v; draw(); });
        numRow(div, '破甲位置 y', e.fragile_pos[1], v => { e.fragile_pos[1] = v; draw(); });
        e.fragile_icon_size ??= e.icon_size;
        numRow(div, '破甲图标尺寸', e.fragile_icon_size, v => e.fragile_icon_size = v);
        e.fragile_num_offset ??= [...e.num_offset];
        numRow(div, '破甲数字偏移 x', e.fragile_num_offset[0], v => { e.fragile_num_offset[0] = v; draw(); });
        numRow(div, '破甲数字偏移 y', e.fragile_num_offset[1], v => { e.fragile_num_offset[1] = v; draw(); });
        e.fragile_sign_offset ??= [0, 0];
        numRow(div, '破甲符号偏移 x', e.fragile_sign_offset[0], v => { e.fragile_sign_offset[0] = v; draw(); });
        numRow(div, '破甲符号偏移 y', e.fragile_sign_offset[1], v => { e.fragile_sign_offset[1] = v; draw(); });
      }
    }
    if (e.kind === 'rarity_flank') {
      numRow(div, '默认间距', e.gap, v => e.gap = v);
      numRow(div, '卡名间距', e.margin ?? 12, v => e.margin = v);
      numRow(div, '尺寸', e.size, v => e.size = v);
    }
    if (e.kind === 'faction') {
      numRow(div, '尺寸', e.size, v => e.size = v);
      selRow(div, '样式', ['1', '2', '3'], String(e.style || 2), v => e.style = parseInt(v, 10));
    }
    if (e.kind === 'duo_frame') {
      // 双式神框 14 参数：pos（上框底图中心，通用行已含）+ 底图大小 + 下框间距 +
      // 框大小 + 上/下内框偏移（相对各自底图中心）+ 上/下外框偏移 y（相对各自底图中心）
      // + 派系标大小/偏移（大小与派系标偏移上下两框共通；仅协战有此元素）
      e.back_size ??= 62;
      numRow(div, '底图大小', e.back_size, v => e.back_size = v);
      e.slot2_dy ??= 74;
      numRow(div, '下框间距', e.slot2_dy, v => { e.slot2_dy = v; draw(); });
      e.frame_size ??= 70;
      numRow(div, '框大小', e.frame_size, v => e.frame_size = v);
      e.frame_offset ??= [0, 0];
      numRow(div, '上内框偏移 x', e.frame_offset[0], v => { e.frame_offset[0] = v; draw(); });
      numRow(div, '上内框偏移 y', e.frame_offset[1], v => { e.frame_offset[1] = v; draw(); });
      e.frame_offset_2 ??= [...e.frame_offset];
      numRow(div, '下内框偏移 x', e.frame_offset_2[0], v => { e.frame_offset_2[0] = v; draw(); });
      numRow(div, '下内框偏移 y', e.frame_offset_2[1], v => { e.frame_offset_2[1] = v; draw(); });
      e.highlight_dy_1 ??= 0;
      numRow(div, '上外框偏移 y', e.highlight_dy_1, v => { e.highlight_dy_1 = v; draw(); });
      e.highlight_dy_2 ??= 0;
      numRow(div, '下外框偏移 y', e.highlight_dy_2, v => { e.highlight_dy_2 = v; draw(); });
      e.faction_size ??= 43;
      numRow(div, '派系标大小', e.faction_size, v => e.faction_size = v);
      e.faction_offset ??= [6, 31];
      numRow(div, '派系标偏移 x', e.faction_offset[0], v => { e.faction_offset[0] = v; draw(); });
      numRow(div, '派系标偏移 y', e.faction_offset[1], v => { e.faction_offset[1] = v; draw(); });
    }
    if (e.kind === 'level_badge') {
      // 等级组件是否绘制由卡面等级决定（等级 0=无等级不绘制），不再提供启用开关
      numRow(div, '底座尺寸', e.base_size, v => e.base_size = v);
      if (!entityLayoutMode) {
        numRow(div, '星标尺寸', e.star_size, v => e.star_size = v);
        e.star_offset ??= [0, 0];
        numRow(div, '星标偏移 x', e.star_offset[0], v => { e.star_offset[0] = v; draw(); });
        numRow(div, '星标偏移 y', e.star_offset[1], v => { e.star_offset[1] = v; draw(); });
      }
      numRow(div, '勾玉尺寸', e.num_size, v => e.num_size = v);
      e.num_offset ??= [0, 0];
      numRow(div, '勾玉偏移 x', e.num_offset[0], v => { e.num_offset[0] = v; draw(); });
      numRow(div, '勾玉偏移 y', e.num_offset[1], v => { e.num_offset[1] = v; draw(); });
    }
    if (e.kind === 'text') {
      numRow(div, '字号', e.font_size, v => e.font_size = v);
      selRow(div, '字体', FONTS, e.font || 'name', v => e.font = v, disp);
    }
  } else {
    const r = layoutRegions()[sel.name];
    if (sel.name === 'art_window') {
      div.appendChild(title('卡图内窗'));
      numRow(div, '中心 x', r.center[0], v => { r.center[0] = v; draw(); });
      numRow(div, '中心 y', r.center[1], v => { r.center[1] = v; draw(); });
      numRow(div, '宽度', r.width, v => { r.width = v; draw(); });
      numRow(div, '高度', r.height, v => { r.height = v; draw(); });
      checkRow(div, '框体居中', r.frame_center, v => { r.frame_center = v; draw(); });
      numRow(div, '纵向偏移', r.offset_y, v => { r.offset_y = v; draw(); });
      return;
    }
    div.appendChild(title(`${disp(sel.name)} 文本区`));
    numRow(div, '中心 x', r.center[0], v => { r.center[0] = v; draw(); });
    numRow(div, '中心 y', r.center[1], v => { r.center[1] = v; draw(); });
    r.center_offset ??= [0, 0];
    numRow(div, '居中点偏移 x', r.center_offset[0], v => { r.center_offset[0] = v; draw(); });
    numRow(div, '居中点偏移 y', r.center_offset[1], v => { r.center_offset[1] = v; draw(); });
    numRow(div, '宽度', r.width, v => { r.width = v; draw(); });
    numRow(div, '高度', r.height, v => { r.height = v; draw(); });
    numRow(div, '字号上限', r.font_range[0], v => r.font_range[0] = v);
    numRow(div, '字号下限', r.font_range[1], v => r.font_range[1] = v);
    checkRow(div, '自动换行', r.wrap, v => r.wrap = v);
    selRow(div, '字体', FONTS, r.font, v => r.font = v, disp);
    r.icon_scale ??= 1.0;
    floatRow(div, '小图标相对文字大小', r.icon_scale, v => r.icon_scale = v);
  }
}
function title(t) { const h = document.createElement('h4'); h.textContent = t; return h; }
function numRow(div, label, val, set) {
  const l = document.createElement('label');
  l.textContent = label + ' ';
  const i = document.createElement('input');
  i.type = 'number'; i.value = val;
  i.onchange = () => { const v = parseInt(i.value, 10); if (isNaN(v)) { i.value = val; return; } markDirty(); set(v); schedulePreview(); };
  l.appendChild(i); div.appendChild(l);
}
function checkRow(div, label, val, set) {
  const l = document.createElement('label');
  l.textContent = label + ' ';
  const i = document.createElement('input');
  i.type = 'checkbox'; i.checked = val;
  i.onchange = () => { markDirty(); set(i.checked); schedulePreview(); };
  l.appendChild(i); div.appendChild(l);
}
function floatRow(div, label, val, set) {
  // 浮点输入（如 icon_scale 比例系数）；非法/非正回退原值
  const l = document.createElement('label');
  l.textContent = label + ' ';
  const i = document.createElement('input');
  i.type = 'number'; i.value = val; i.step = 0.05;
  i.onchange = () => { const v = parseFloat(i.value); if (isNaN(v) || v <= 0) { i.value = val; return; } markDirty(); set(v); schedulePreview(); };
  l.appendChild(i); div.appendChild(l);
}
function selRow(div, label, opts, val, set, map = null) {
  const l = document.createElement('label');
  l.textContent = label + ' ';
  const s = document.createElement('select');
  for (const o of opts) {
    const op = document.createElement('option');
    op.value = o;
    op.textContent = map ? map(o) : o;  // map：内部值 → 中文显示名（值保持内部键不变）
    if (o === val) op.selected = true;
    s.appendChild(op);
  }
  s.onchange = () => { markDirty(); set(s.value); schedulePreview(); };
  l.appendChild(s); div.appendChild(l);
}

// ---- 单卡布局模式：进入/退出/保存 ----
// 深合并：卡面 layout 稀疏覆盖段叠加到该卡类型与框品的全局布局
function mergeLayoutJS(base, override) {
  const merged = deepCopy(base);
  if (!override || typeof override !== 'object') return merged;
  for (const sec of ['elements', 'text_regions']) {
    const items = override[sec];
    if (!items || typeof items !== 'object') continue;
    for (const [name, item] of Object.entries(items)) {
      if (item && typeof item === 'object' && !Array.isArray(item))
        merged[sec][name] = {...(merged[sec][name] || {}), ...item};
    }
  }
  return merged;
}
// 稀疏化：只保留与全局布局不同的键（保存时不写相同项；全部相同返回 null → 删 layout 键）
function diffLayout(eff, base) {
  const out = {};
  for (const sec of ['elements', 'text_regions']) {
    for (const [name, item] of Object.entries((eff || {})[sec] || {})) {
      const b = ((base || {})[sec] || {})[name] || {};
      const diff = {};
      for (const [k, v] of Object.entries(item)) {
        if (JSON.stringify(v) !== JSON.stringify(b[k])) diff[k] = v;
      }
      if (Object.keys(diff).length) (out[sec] = out[sec] || {})[name] = diff;
    }
  }
  return Object.keys(out).length ? out : null;
}
function layoutSavePayload() {
  const payload = deepCopy(layouts);
  for (const t of TYPES) {
    const base = payload[t];
    if (!base || !base.frame_variants) continue;
    for (const [variant, effective] of Object.entries(base.frame_variants)) {
      const sparse = diffLayout(effective, base);
      if (sparse) base.frame_variants[variant] = sparse;
      else delete base.frame_variants[variant];
    }
    if (!Object.keys(base.frame_variants).length) delete base.frame_variants;
  }
  return payload;
}
function singleGlobalLayout() {
  return layoutForRender(globalTypeLayout(formData.type, formData.frame_variant ?? 'norm'));
}
async function enterCardLayout() {
  if (!formData || !curCard || cardLayoutMode) return;
  try { await ensureLayouts(); } catch (e) { listErr(['布局加载失败: ' + e]); return; }
  if (!layouts[formData.type]) { listErr([`布局缺失类型：${formData.type}`]); return; }
  cardLayoutMode = curCard;
  singleLayout = mergeLayoutJS(singleGlobalLayout(), formData.layout);
  singleSnapshot = deepCopy(singleLayout);
  singleDirty = false;
  curType = formData.type;
  layoutFrameVariant = formData.frame_variant ?? 'norm';
  sel = null; previewImg = null;
  updateLayoutNavtab();
  document.getElementById('l-btn-save').textContent = '保存并返回';
  showTab('layout');
  if (layoutInited) { buildTypes(); selectType(curType); }  // 非首次：layoutBoot 不走，手动重建
}
function exitCardLayout() {
  cardLayoutMode = null; singleLayout = null; singleSnapshot = null; singleDirty = false;
  updateLayoutNavtab();
  document.getElementById('l-btn-save').textContent = '保存';
}
async function saveCardLayout() {
  const ov = diffLayout(singleLayout, singleGlobalLayout());
  if (ov) formData.layout = ov; else delete formData.layout;
  const ok = await saveCard();  // 校验/保存失败：留在单卡模式，错误已在表单栏显示
  if (!ok) return;
  exitCardLayout();
  showTab('cards');  // saveCard 已刷新列表并选中该卡
}

// 保存
document.getElementById('l-btn-save').onclick = async () => {
  if (cardLayoutMode) return saveCardLayout();
  let r;
  try {
    r = await fetch('/api/layout', {method: 'PUT',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify(layoutSavePayload())});
  } catch (e) {
    statusEl.textContent = '保存请求失败: ' + e;
    return;
  }
  if (r.ok) { dirty = false; layoutSnapshot = deepCopy(layouts); statusEl.textContent = '已保存'; }
  else statusEl.textContent = '保存失败: ' + (await r.json()).detail;
};
document.getElementById('l-btn-preview').onclick = refreshPreview;
