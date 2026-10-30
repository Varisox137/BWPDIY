// ================= 卡牌库 tab =================
let projects = [];
let curProject = null;
let cards = {shikigami: [], cards: []};  // list_cards 结构：两组 [{stem, name}]（name 为 null = 文件损坏）
let curCard = null;    // 当前卡的 stem（文件名，不含扩展名）；卡名以文件内 name 字段为准
let cardData = null;   // 服务端已保存内容
let formData = null;   // 编辑副本（保存前不落盘）
// ---- 撤回栈（卡牌表单）：鼠标操作与输入框编辑通用；爆发合并——间隔 ≤800ms 的连续编辑只记一次前态快照 ----
let undoStack = [];
let prevFormSnap = null;  // 上一爆发结束时的表单状态（= 下一爆发的编辑前状态）
let lastEditAt = 0;
const UNDO_GAP = 800, UNDO_CAP = 50;
function resetUndo() {
  undoStack = [];
  prevFormSnap = formData ? deepCopy(formData) : null;
  lastEditAt = 0;
}
function noteEdit() {  // 每次表单变更后调用（afterEdit/afterMouseEdit 统一入口）
  contentRev++;
  const now = Date.now();
  if (prevFormSnap && now - lastEditAt > UNDO_GAP) {
    undoStack.push(prevFormSnap);
    if (undoStack.length > UNDO_CAP) undoStack.shift();
  }
  lastEditAt = now;
  prevFormSnap = deepCopy(formData);
}
function undoLast() {  // 撤回上次修改（撤回动作本身不入栈）
  if (!formData || !undoStack.length) { cStatusEl.textContent = '没有可撤回的修改'; return; }
  formData = undoStack.pop();
  prevFormSnap = deepCopy(formData); lastEditAt = Date.now();
  cDirty = true;  // 保守标脏：不逐一比对是否恰好回到已保存态
  buildForm();
  scheduleCardPreview();
}
function undoAll() {  // 撤回全部修改 = 恢复到上次保存/加载的状态
  if (!formData || !cardData) return;
  if (!cDirty) { cStatusEl.textContent = '没有未保存的修改'; return; }
  if (!confirm('撤回全部未保存修改，恢复到上次保存的状态？')) return;
  formData = deepCopy(cardData);
  resetUndo();
  cDirty = false;
  buildForm();
  scheduleCardPreview();
}
let cDirty = false;
let contentRev = 0;  // 写盘响应返回时识别期间是否又有键盘/程序化编辑
// ---- 机制（灵咒/关键字/加护蚀印描述框）：全局共享池，不随项目切换；与选中卡牌互斥 ----
let mechs = [];        // 机制列表（{stem, name}，与卡牌列表同口径）
let curMech = null;    // 当前选中机制名
let mechData = null;   // 服务端已保存内容
let mechForm = null;   // 编辑副本（保存前不落盘）
let mDirty = false;
const cStatusEl = document.getElementById('c-status');
const cErrorEl = document.getElementById('c-error');
const cPreviewErrors = {main: '', entity: ''};
let cPreviewErrorChannel = null;
function setPreviewError(channel, text) {
  const other = channel === 'main' ? 'entity' : 'main';
  cPreviewErrors[channel] = text;
  if (text) cPreviewErrorChannel = channel;
  else if (cPreviewErrorChannel === channel)
    cPreviewErrorChannel = cPreviewErrors[other] ? other : null;
  cErrorEl.textContent = cPreviewErrorChannel ? cPreviewErrors[cPreviewErrorChannel] : '';
}
const cPreviewImg = document.getElementById('c-preview');
let cPreviewTimer = null;
let cPreviewSeq = 0;   // 请求序号持续增长；已处理序号只拦截逆序旧响应，避免连续编辑时无中间画面
let cPreviewAppliedSeq = 0;
let cPreviewUrl = null;  // 当前预览 objectURL：换图时释放上一张，防内存累积
let selectSeq = 0;     // 选卡请求序号：快速连点时慢响应不得覆盖新卡表单

function listErr(msgs) {
  document.getElementById('c-list-error').textContent = (msgs || []).join('\n');
}
function showFormErrors(msgs) {
  const el = document.getElementById('c-form-errors');
  if (el) el.textContent = (msgs || []).join('\n');
}
const sessionPromptSuppressed = {naming: false, unsaved: false};
let sessionConfirmState = null;
function sessionConfirm(message, kind) {
  if (sessionPromptSuppressed[kind]) return Promise.resolve(true);
  if (sessionConfirmState) return Promise.resolve(false);
  const modal = document.getElementById('session-confirm-modal');
  document.getElementById('session-confirm-text').textContent = message;
  document.getElementById('session-confirm-suppress').checked = false;
  modal.style.display = 'block';
  return new Promise(resolve => { sessionConfirmState = {kind, resolve}; });
}
function finishSessionConfirm(ok) {
  const state = sessionConfirmState;
  if (!state) return;
  if (ok && document.getElementById('session-confirm-suppress').checked) {
    sessionPromptSuppressed[state.kind] = true;
  }
  sessionConfirmState = null;
  document.getElementById('session-confirm-modal').style.display = 'none';
  state.resolve(ok);
}
document.getElementById('session-confirm-ok').onclick = () => finishSessionConfirm(true);
document.getElementById('session-confirm-cancel').onclick = () => finishSessionConfirm(false);
async function confirmDiscard() {
  if (askBusy() || storageBusy()) return false;
  if (cDirty && !await sessionConfirm('当前卡牌有未保存修改，切换将丢弃，继续？', 'unsaved')) return false;
  if (mDirty && !await sessionConfirm('当前机制有未保存修改，切换将丢弃，继续？', 'unsaved')) return false;
  return true;
}

// ---- 项目列表 ----
async function loadProjects(selectStem = null) {
  let r;
  try { r = await fetch('/api/projects'); } catch (e) { listErr(['项目列表请求失败: ' + e]); return; }
  projects = await r.json();
  if (!projects.includes(curProject)) curProject = null;
  buildProjectList();
  if (curProject) await loadCards(selectStem);
  else { cards = {shikigami: [], cards: []}; buildCardList(); if (!curMech) clearCard(); }  // 机制编辑态不抢占右栏
}
function fitListHeight(div) {
  const items = div.children;
  div.style.maxHeight = items.length > 8
    ? `${items[7].offsetTop + items[7].offsetHeight - items[0].offsetTop}px` : 'none';
  return div.style;
}
function buildProjectList() {
  document.getElementById('c-proj-secs').style.display = curProject ? '' : 'none';  // 未选中项目时不显示式神/卡牌栏
  const div = document.getElementById('c-projects');
  div.innerHTML = '';
  for (const p of projects) {
    const d = document.createElement('div');
    d.textContent = p;
    d.className = 'item' + (p === curProject ? ' active' : '');
    d.onclick = () => selectProject(p);
    div.appendChild(d);
  }
  fitListHeight(div);
}
async function selectProject(p) {
  if (p === curProject || !await confirmDiscard()) return;
  cDirty = false;
  mainShiki = null; neutralMode = false;
  curProject = p;
  listErr([]);
  buildProjectList();
  await loadCards();
}

// ---- 卡牌列表 ----
async function loadCards(selectStem = null) {
  let r;
  try { r = await fetch(`/api/projects/${enc(curProject)}/cards`); }
  catch (e) { listErr(['卡牌列表请求失败: ' + e]); return; }
  if (!r.ok) { cards = {shikigami: [], cards: []}; buildCardList(); if (!curMech) clearCard(); listErr(await parseErrorDetail(r)); return; }
  cards = await r.json();
  if (mainShiki && !shikiGroupByName(mainShiki)) mainShiki = null;  // 主要式神已删除：解除筛选
  buildCardList();
  if (curMech) return;  // 机制为全局池：机制编辑态下切项目/刷列表不自动选卡抢占右栏
  const all = [...cards.shikigami, ...cards.cards];
  const stems = new Set(all.flatMap(c => (c.versions || []).map(v => v.stem)));
  const target = selectStem && stems.has(selectStem) ? selectStem
    : (all.length ? all[0].stem : null);
  if (target) await selectCard(target, true);
  else clearCard();
}
// 当前项目式神名列表（所属式神下拉选项来源；损坏文件无 name 不提供）
function shikigamiNames() {
  return cards.shikigami.map(c => c.name).filter(n => n != null);
}
// 主要式神筛选（v1.6.2）：选中某主要式神后卡牌栏只显示其所属卡（协战任一命中即算），
// 该选择独立于 curCard（点选其他卡仍保持）；「显示中立牌」进入中立模式（无所属式神的卡），
// 再点「显示全部卡牌」或选中任一条目退出。列表按 id 升序（无 id 在后按名称，store 已排好）。
let mainShiki = null;   // 当前主要式神名（筛选上下文）
let neutralMode = false;
function shikiGroupByName(name) { return cards.shikigami.find(g => g.name === name) || null; }
function shikiDeckValid(shikiName, groups) {
  const owned = groups.filter(g => g.name != null && (g.versions || []).some(v =>
    [v.shikigami, v.shikigami1, v.shikigami2].includes(shikiName)));
  const dates = [...new Set(owned.flatMap(g => (g.versions || [])
    .map(v => v.date).filter(Boolean)))].sort();
  if (!dates.length) dates.push('');
  for (const date of dates) {
    const rarities = [];
    for (const group of owned) {
      const version = (group.versions || []).find(v => !v.date || !date || v.date <= date);
      if (!version || version.type === '式神' || version.shikigami1 || version.shikigami2
          || version.shikigami !== shikiName) continue;  // 协战/衍生物式神不计入稀有度校验
      rarities.push(version.rarity);
    }
    if (rarities.filter(r => r === 'R').length < 4
        || rarities.filter(r => r === 'SR').length < 3
        || rarities.filter(r => r === 'SSR').length < 1) return false;
  }
  return true;
}
function syncDeleteButtons() {
  const hasStem = (group, stem) => !!stem && group.some(e =>
    (e.versions || [{stem: e.stem}]).some(v => v.stem === stem));
  const visible = {
    'c-del-shiki': !curMech && hasStem(cards.shikigami, curCard),
    'c-del-card': !curMech && hasStem(cards.cards, curCard),
    'c-del-mech': !!curMech,
  };
  for (const [id, show] of Object.entries(visible)) {
    const button = document.getElementById(id);
    button.style.display = show ? '' : 'none';
    button.disabled = !show;
  }
}
function buildCardList() {
  const shikiDiv = document.getElementById('c-shikigami');
  const div = document.getElementById('c-cards');
  shikiDiv.innerHTML = '';
  div.innerHTML = '';
  for (const c of cards.shikigami) shikiDiv.appendChild(cardItem(c, true));
  let visible = cards.cards;
  if (neutralMode) visible = visible.filter(c => !c.shikigami && !c.shikigami1 && !c.shikigami2);
  else if (mainShiki) {
    visible = visible.filter(c => [c.shikigami, c.shikigami1, c.shikigami2].includes(mainShiki));
  }
  for (const c of visible) div.appendChild(cardItem(c, false));
  document.getElementById('c-shiki-count').textContent = `${cards.shikigami.length}/49`;
  // 数量常驻=项目总组数/299（上限按组计）；有筛选时附「筛选：当前可见数」
  document.getElementById('c-card-count').textContent = (neutralMode || mainShiki)
    ? `${cards.cards.length}/299（筛选：${visible.length}）` : `${cards.cards.length}/299`;
  document.getElementById('c-neutral').textContent = neutralMode ? '显示全部卡牌' : '显示中立牌';
  fitListHeight(shikiDiv); fitListHeight(div);
  syncDeleteButtons();
}
function entryItem(c, activeStem) {
  // 分组条目（v1.6.0）：卡名(id)（id 空不显示）+ 右侧非加粗 (版本数)；
  // 点击编辑最新版本（c.stem）；同组任一版本被选中均高亮
  const d = document.createElement('div');
  d.title = c.stem;  // title 附文件名（显示名为卡内 name，与文件名脱钩）
  if (c.name == null) {  // 文件损坏（yaml 无法解析/缺 name）：显示 stem 并标红
    d.textContent = c.stem;
    d.title += '（文件损坏，无法读取卡名）';
    d.className = 'item broken';
  } else {
    d.className = 'item';
    const left = document.createElement('span');
    left.textContent = c.name;
    if (c.id) {
      const idSpan = document.createElement('span');
      idSpan.className = 'meta';
      idSpan.textContent = `(${c.id})`;
      left.appendChild(idSpan);
    }
    const count = document.createElement('span');
    count.className = 'meta';
    count.textContent = `(${c.count})`;
    d.appendChild(left); d.appendChild(count);
  }
  if ((c.versions || [{stem: c.stem}]).some(v => v.stem === activeStem)) d.classList.add('active');
  return d;
}
function cardItem(c, isShiki) {
  const d = entryItem(c, curCard);
  if (isShiki && c.name != null) {
    d.classList.add('shiki');
    if (!shikiDeckValid(c.name, cards.cards)) {
      const count = d.lastElementChild;
      count.classList.add('deck-invalid');
      count.title = '卡组校验未通过：每个版本日期在排除协战/衍生物式神后，至少须有 4R/3SR/1SSR';
    }
  }
  d.onclick = () => selectCard(c.stem);
  return d;
}
async function selectCard(stem, force = false) {
  if (!force && (stem === curCard || !await confirmDiscard())) return;
  if (curMech) exitMech();  // 选中卡牌与选中机制互斥（mDirty 守卫已在 confirmDiscard 完成）
  cPreviewSeq++; cPreviewAppliedSeq = cPreviewSeq;
  cEntitySeq++; cEntityAppliedSeq = cEntitySeq;
  cPortraitSeq++; cPortraitAppliedSeq = cPortraitSeq;
  curCard = stem;
  const sg = cards.shikigami.find(e => (e.versions || []).some(v => v.stem === stem));
  if (sg) mainShiki = sg.name;
  neutralMode = false;
  buildCardList();
  listErr([]);
  cStatusEl.textContent = '';
  const seq = ++selectSeq;
  let r;
  try { r = await fetch(`/api/projects/${enc(curProject)}/cards/${enc(stem)}`); }
  catch (e) { if (seq === selectSeq) { clearCard(); listErr(['卡牌读取请求失败: ' + e]); } return; }
  if (seq !== selectSeq) return;  // 期间又选了别的卡，丢弃本次慢响应
  if (!r.ok) { clearCard(); listErr(await parseErrorDetail(r)); return; }
  const data = await r.json();
  if (seq !== selectSeq) return;  // JSON 解析期间又选了别的卡，旧数据不得提交
  cardData = data;
  formData = deepCopy(cardData);
  entityState = entityEligible(formData) ? makeEntityState(formData) : null;
  cDirty = false;
  resetUndo();
  buildForm();
  cPreviewProject();
}
function clearCard() {
  if (activeAsk) return;  // 输入框挂载在表单内时，任何重建都不得将其销毁
  selectSeq++;
  clearTimeout(cPreviewTimer);
  clearTimeout(cPortraitTimer);
  clearTimeout(cEntityTimer);
  cPreviewTimer = cPortraitTimer = cEntityTimer = null;
  for (const channel of ['art', 'entity', 'portrait']) {
    if (mousePreviewFrames[channel]) cancelAnimationFrame(mousePreviewFrames[channel]);
    mousePreviewFrames[channel] = 0;
  }
  cPreviewSeq++; cPreviewAppliedSeq = cPreviewSeq;
  cPortraitSeq++; cPortraitAppliedSeq = cPortraitSeq;
  cEntitySeq++; cEntityAppliedSeq = cEntitySeq;
  curCard = null; cardData = null; formData = null; entityState = null; cDirty = false;
  resetUndo();
  document.getElementById('c-form').textContent = '未选中卡牌';
  syncCardFrameButtons();
  cPreviewImg.removeAttribute('src');
  cPortraitImg.style.display = 'none';
  cPortraitImg.removeAttribute('src');
  cEntityImg.style.display = 'none';
  cEntityImg.removeAttribute('src');
  cSubpreviews.style.display = 'none';
  if (cPortraitUrl) { URL.revokeObjectURL(cPortraitUrl); cPortraitUrl = null; }
  if (cEntityUrl) { URL.revokeObjectURL(cEntityUrl); cEntityUrl = null; }
  if (cPreviewUrl) { URL.revokeObjectURL(cPreviewUrl); cPreviewUrl = null; }
  cPreviewErrors.main = ''; cPreviewErrors.entity = ''; cPreviewErrorChannel = null;
  cErrorEl.textContent = '';
}

// ---- 项目/卡牌操作（新建/重命名/删除） ----
// 所有内联输入共用一把交互锁：未确定/取消时禁止其他操作，避免表单重建销毁输入框、
// Promise 永久等待；锁由两套输入框（通用 ask / 新建卡牌 askNewCard）共同遵守。
let activeAsk = null;
function askBusy() {
  if (!activeAsk) return false;
  showFormErrors([`请先确定或取消「${activeAsk.title}」输入，再进行其他操作。`]);
  guiDebug('input.blocked', activeAsk.title);
  return true;
}
function storageBusy() {
  if (!pendingStorageWrites) return false;
  showFormErrors(['上一次本地写盘尚未完成，请稍候再进行其他操作。']);
  guiDebug('storage.blocked', `pending=${pendingStorageWrites}`);
  return true;
}
function beginAsk(title) {
  if (askBusy() || storageBusy()) return false;
  activeAsk = {title};
  guiDebug('input.open', title);
  return true;
}
function endAsk() {
  if (activeAsk) guiDebug('input.close', activeAsk.title);
  activeAsk = null;
}
document.addEventListener('click', ev => {
  if (activeAsk) {
    if (document.getElementById('c-ask').contains(ev.target)) return;
    ev.preventDefault(); ev.stopImmediatePropagation(); askBusy();
    return;
  }
  if (pendingStorageWrites) {
    ev.preventDefault(); ev.stopImmediatePropagation(); storageBusy();
  }
}, true);
// 通用内联输入条：标题 + 文本框 + 可选下拉（selDefault 默认选中），确定/取消
function ask({title, value = '', options = null, selDefault = null, target}) {
  return new Promise(resolve => {
    if (!beginAsk(title)) { resolve(null); return; }
    const box = document.getElementById('c-ask');
    document.getElementById(target).appendChild(box);
    box.innerHTML = '';
    box.style.display = 'block';
    const t = document.createElement('div');
    t.textContent = title;
    box.appendChild(t);
    const input = document.createElement('input');
    input.type = 'text'; input.value = value;
    box.appendChild(input);
    let sel = null;
    if (options) {
      sel = document.createElement('select');
      for (const o of options) {
        const op = document.createElement('option');
        op.value = op.textContent = o;
        sel.appendChild(op);
      }
      if (selDefault) sel.value = selDefault;
      box.appendChild(sel);
    }
    const row = document.createElement('div');
    const ok = document.createElement('button'); ok.textContent = '确定';
    const cancel = document.createElement('button'); cancel.textContent = '取消';
    row.appendChild(ok); row.appendChild(cancel);
    box.appendChild(row);
    input.focus(); input.select();
    let settled = false;
    const done = v => {
      if (settled) return;
      settled = true;
      endAsk();
      document.getElementById('c-ask-home').appendChild(box);
      box.style.display = 'none'; box.innerHTML = ''; resolve(v);
    };
    ok.onclick = () => done({text: input.value, sel: sel ? sel.value : null});
    cancel.onclick = () => done(null);
    input.onkeydown = ev => {
      if (ev.key === 'Enter') ok.click();
      if (ev.key === 'Escape') cancel.click();
    };
  });
}

function isReservedProjectName(name) {
  return name.trim().toLowerCase() === 'mechanisms';
}
function rejectReservedProjectName(name) {
  if (!isReservedProjectName(name)) return false;
  alert('项目名「mechanisms」是跨项目通用机制的保留目录，请更换项目名。');
  return true;
}
document.getElementById('c-new-proj').onclick = async () => {
  const r = await ask({title: '新项目名', target: 'c-ask-project'});
  if (!r || !r.text || rejectReservedProjectName(r.text)) return;
  const resp = await fetch('/api/projects', {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name: r.text})});
  if (!resp.ok) { listErr(await parseErrorDetail(resp)); return; }
  curProject = r.text; cDirty = false;
  listErr([]);
  await loadProjects();
};
document.getElementById('c-ren-proj').onclick = async () => {
  if (!curProject) { listErr(['请先选择项目']); return; }
  const r = await ask({title: `重命名项目「${curProject}」为`, value: curProject,
    target: 'c-ask-project'});
  if (!r || !r.text || r.text === curProject || rejectReservedProjectName(r.text)) return;
  if (cDirty && !await sessionConfirm('当前卡牌有未保存修改，项目重命名后将丢弃，继续？', 'unsaved')) return;
  const resp = await fetch(`/api/projects/${enc(curProject)}`, {method: 'PUT',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({new_name: r.text})});
  if (!resp.ok) { listErr(await parseErrorDetail(resp)); return; }
  const keep = curCard;  // 重命名后保持当前卡选中（loadCards 缺省会跳第一张卡）
  curProject = r.text; cDirty = false;
  listErr([]);
  await loadProjects(keep);
};
document.getElementById('c-del-proj').onclick = async () => {
  if (!curProject) { listErr(['请先选择项目']); return; }
  if (!confirm(`删除项目「${curProject}」及其全部卡牌？`)) return;
  const resp = await fetch(`/api/projects/${enc(curProject)}`, {method: 'DELETE'});
  if (!resp.ok) { listErr(await parseErrorDetail(resp)); return; }
  curProject = null; cDirty = false;
  listErr([]);
  await loadProjects();
};

// 新卡骨架：类型创建时定死；所属式神按下拉/手动填写结果填入（不再默认 = 项目名）
function skeleton(type, name, shiki = {}) {
  if (type === '式神') return Object.assign(
    {type, name, faction: '红莲', power: 3, health: 4, description: ''}, shiki);
  const c = {type, name, level: 1, rarity: 'R', description: ''};
  Object.assign(c, shiki);  // 协战 → shikigami1/shikigami2；其余 → shikigami
  if (type === '战斗') { c['power+'] = 0; c['shield+'] = 0; }
  if (type === '形态') { c.power = 1; c.health = 1; }
  if (type === '幻境') c.durability = 1;
  return c;
}
// 文件名 stem：卡名去路径非法字符；冲突追加 -2/-3…（前端先按已拉列表查重，后端校验兜底）
function sanitizeStem(name) {
  const s = name.replace(/[\\/:*?"<>|]/g, '').trim().replace(/[. ]+$/, '');
  return s || 'card';
}
function uniqueStem(base) {
  const used = new Set([...cards.shikigami, ...cards.cards].flatMap(c => (c.versions || []).map(v => v.stem)));
  if (!used.has(base)) return base;
  for (let i = 2; ; i++) {
    const s = `${base}-${i}`;
    if (!used.has(s)) return s;
  }
}
// 新建卡牌专用对话框：类型六项 + 卡名 + 按类型的所属式神选择（不走通用 ask，项目场景还在用）
function askNewCard(target) {
  const MANUAL = '（手动填写）';
  const title = '新建卡牌（卡名 + 类型）';
  return new Promise(resolve => {
    if (!beginAsk(title)) { resolve(null); return; }
    const box = document.getElementById('c-ask');
    document.getElementById(target).appendChild(box);
    box.innerHTML = '';
    box.style.display = 'block';
    const t = document.createElement('div');
    t.textContent = title;
    box.appendChild(t);
    const nameInput = document.createElement('input');
    nameInput.type = 'text'; nameInput.placeholder = '卡名';
    box.appendChild(nameInput);
    const typeSel = document.createElement('select');
    for (const o of TYPES) {
      const op = document.createElement('option');
      op.value = op.textContent = o;
      if (o === '式神') op.selected = true;
      typeSel.appendChild(op);
    }
    box.appendChild(typeSel);
    const shikiBox = document.createElement('div');
    box.appendChild(shikiBox);
    const names = shikigamiNames();
    // 式神下拉 + 手动填写组合；返回当前取值（手动空串 = 不填）
    const combo = label => {
      const l = document.createElement('label');
      l.textContent = label + ' ';
      const s = document.createElement('select');
      for (const o of [MANUAL, ...names]) {
        const op = document.createElement('option');
        op.value = op.textContent = o;
        s.appendChild(op);
      }
      const i = document.createElement('input');
      i.type = 'text'; i.placeholder = '式神名';
      s.onchange = () => { i.style.display = s.value === MANUAL ? '' : 'none'; };
      l.appendChild(s); l.appendChild(i);
      shikiBox.appendChild(l);
      return () => s.value === MANUAL ? i.value.trim() : s.value;
    };
    let getters = [];
    const rebuildShiki = () => {
      shikiBox.innerHTML = '';
      const tp = typeSel.value;
      if (tp === '协战') getters = [['shikigami1', combo('所属式神1')], ['shikigami2', combo('所属式神2')]];
      else if (mainShiki) {
        // 已选主要式神：免填所属式神，自动适配（协战除外）
        const note = document.createElement('div');
        note.textContent = `所属式神：${mainShiki}（当前主要式神）`;
        shikiBox.appendChild(note);
        getters = [['shikigami', () => mainShiki]];
      } else getters = [['shikigami', combo('所属式神')]];
    };
    typeSel.onchange = rebuildShiki;
    rebuildShiki();
    const row = document.createElement('div');
    const ok = document.createElement('button'); ok.textContent = '确定';
    const cancel = document.createElement('button'); cancel.textContent = '取消';
    row.appendChild(ok); row.appendChild(cancel);
    box.appendChild(row);
    nameInput.focus();
    let settled = false;
    const done = v => {
      if (settled) return;
      settled = true;
      endAsk();
      document.getElementById('c-ask-home').appendChild(box);
      box.style.display = 'none'; box.innerHTML = ''; resolve(v);
    };
    ok.onclick = () => {
      const shiki = {};
      for (const [k, get] of getters) { const v = get(); if (v) shiki[k] = v; }
      done({name: nameInput.value.trim(), type: typeSel.value, shiki});
    };
    cancel.onclick = () => done(null);
    nameInput.onkeydown = ev => {
      if (ev.key === 'Enter') ok.click();
      if (ev.key === 'Escape') cancel.click();
    };
  });
}
document.getElementById('c-new-card').onclick = async () => {
  if (!curProject) { listErr(['请先选择项目']); return; }
  const r = await askNewCard('c-ask-card');
  if (!r || !r.name) return;
  const stem = uniqueStem(sanitizeStem(r.name));
  const newCard = skeleton(r.type, r.name, r.shiki);
  if (mainShiki) {
    // 版本日期优先复制当前主要式神的最早版本日期（无则留空=保存时取当天）
    const g = shikiGroupByName(mainShiki);
    const dates = g ? g.versions.map(v => v.date).filter(Boolean).sort() : [];
    if (dates.length) newCard.version_date = dates[0];
  }
  const resp = await fetch(`/api/projects/${enc(curProject)}/cards/${enc(stem)}`, {method: 'PUT',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(newCard)});
  if (!resp.ok) { listErr(await parseErrorDetail(resp)); return; }
  listErr([]);
  await loadCards(stem);
};
document.getElementById('c-new-shiki').onclick = async () => {
  if (!curProject) { listErr(['请先选择项目']); return; }
  const r = await ask({title: '新建式神（卡名）', target: 'c-ask-shiki'});
  if (!r || !r.text) return;
  const name = r.text.trim();
  if (!name) return;
  const stem = uniqueStem(sanitizeStem(name));
  const resp = await fetch(`/api/projects/${enc(curProject)}/cards/${enc(stem)}`, {method: 'PUT',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(skeleton('式神', name))});
  if (!resp.ok) { listErr(await parseErrorDetail(resp)); return; }
  listErr([]);
  await loadCards(stem);
};
document.getElementById('c-del-shiki').onclick = () => {
  if (!curCard || !cards.shikigami.some(e => (e.versions || []).some(v => v.stem === curCard))) {
    listErr(['请先选择主要式神']); return;
  }
  document.getElementById('c-del-card').onclick();
};
document.getElementById('c-neutral').onclick = () => {
  if (neutralMode) { neutralMode = false; buildCardList(); return; }
  neutralMode = true;
  mainShiki = null;  // 取消主要式神选择（同步隐藏其专属牌），转为显示全部中立牌
  clearCard();
  buildCardList();
};
document.getElementById('c-del-card').onclick = async () => {
  if (!curCard) { listErr(['请先选择卡牌']); return; }
  const shown = formData && formData.name ? formData.name : curCard;
  if (!confirm(`删除卡牌「${shown}」？`)) return;
  const resp = await fetch(`/api/projects/${enc(curProject)}/cards/${enc(curCard)}`, {method: 'DELETE'});
  if (!resp.ok) { listErr(await parseErrorDetail(resp)); return; }
  cDirty = false; curCard = null;
  listErr([]);
  await loadCards();
};

// ---- 中栏预览：主卡/头像/对局式神各有独立防抖、序号与 objectURL ----
const cSubpreviews = document.getElementById('c-subpreviews');
const cEntityImg = document.getElementById('c-entity');
let cEntityTimer = null, cEntitySeq = 0, cEntityAppliedSeq = 0, cEntityUrl = null;
function syncSubpreviews() {
  const visible = cPortraitImg.style.display !== 'none' || cEntityImg.style.display !== 'none';
  cSubpreviews.style.display = visible ? 'flex' : 'none';
}
function scheduleCardPreview() {
  clearTimeout(cPreviewTimer);
  cPreviewTimer = setTimeout(() => {
    cPreviewTimer = null;
    return cPreviewForm();
  }, 300);
}
function scheduleEntityPreview() {
  clearTimeout(cEntityTimer);
  cEntityTimer = setTimeout(() => {
    cEntityTimer = null;
    return entityPreview();
  }, 300);
}
async function cHandlePreviewResponse(r, seq) {
  if (seq <= cPreviewAppliedSeq) return;  // 只拦截逆序旧响应；连续编辑时仍显示最新已完成画面
  if (!r.ok) {
    const detail = await parseErrorDetail(r);
    if (seq <= cPreviewAppliedSeq) return;
    cPreviewAppliedSeq = seq;
    setPreviewError('main', '预览失败：' + detail.join('\n'));
    return;
  }
  const blob = await r.blob();
  if (seq <= cPreviewAppliedSeq) return;
  cPreviewAppliedSeq = seq;
  setPreviewError('main', '');
  const url = URL.createObjectURL(blob);
  const prev = cPreviewUrl;
  cPreviewUrl = url;
  cPreviewImg.src = url;
  if (prev) URL.revokeObjectURL(prev);
}
async function cHandleEntityPreviewResponse(r, seq) {
  if (seq <= cEntityAppliedSeq) return;
  if (!r.ok) {
    const detail = await parseErrorDetail(r);
    if (seq <= cEntityAppliedSeq) return;
    cEntityAppliedSeq = seq;
    setPreviewError('entity', '对局式神预览失败：' + detail.join('\n'));
    return;
  }
  const blob = await r.blob();
  if (seq <= cEntityAppliedSeq) return;
  cEntityAppliedSeq = seq;
  setPreviewError('entity', '');
  const url = URL.createObjectURL(blob);
  const prev = cEntityUrl;
  cEntityUrl = url;
  cEntityImg.src = url;
  if (prev) URL.revokeObjectURL(prev);
}
async function cPreviewProject() {
  if (!curProject || !curCard) return;
  entityPreview();
  cPreviewPortrait(false);
  const seq = ++cPreviewSeq;
  let r;
  try {
    r = await fetch(`/api/projects/${enc(curProject)}/cards/${enc(curCard)}/preview`, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'});
  } catch (e) {
    if (seq === cPreviewSeq) setPreviewError('main', '预览请求失败: ' + e);
    return;
  }
  await cHandlePreviewResponse(r, seq);
}
async function cPreviewForm(withPortrait = true, withEntity = true) {
  if (!formData || !curProject || !curCard) return;
  if (validateCardJS(formData).length) return;  // 表单校验未过：不刷预览（错误已在表单侧显示）
  if (withEntity) entityPreview();
  if (withPortrait) cPreviewPortrait(true);  // 鼠标预览按独立通道跳过另一侧重渲
  const seq = ++cPreviewSeq;
  let r;
  try {
    // 走项目卡预览（基准目录=项目 images/），表单整体覆盖：卡图 offset/scale 修改实时可见；
    // 不传 layout——服务端自动把卡面 layout 段（单卡布局覆盖）合并到该类型全局布局
    r = await fetch(`/api/projects/${enc(curProject)}/cards/${enc(curCard)}/preview`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({card: formData})});
  } catch (e) {
    if (seq === cPreviewSeq) setPreviewError('main', '预览请求失败: ' + e);
    return;
  }
  await cHandlePreviewResponse(r, seq);
}
async function entityPreview() {
  const seq = ++cEntitySeq;
  if (!formData || !curProject || !curCard || !entityEligible(formData)) {
    cEntityAppliedSeq = seq;
    cEntityImg.style.display = 'none';
    cEntityImg.removeAttribute('src');
    if (cEntityUrl) { URL.revokeObjectURL(cEntityUrl); cEntityUrl = null; }
    syncSubpreviews();
    return;
  }
  if (!entityState) entityState = makeEntityState(formData);
  cEntityImg.style.display = 'block';
  syncSubpreviews();
  let r;
  try {
    r = await fetch('/api/entity-preview', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({project: curProject, card: formData, state: entityState})});
  } catch (e) {
    if (seq === cEntitySeq) setPreviewError('entity', '对局式神预览请求失败: ' + e);
    return;
  }
  await cHandleEntityPreviewResponse(r, seq);
}
document.getElementById('c-btn-refresh').onclick = () => {
  if (curMech) {  // 机制编辑态：有未保存修改时刷新表单覆盖预览，避免被已保存内容覆盖
    if (mDirty) scheduleMechPreview(); else mechPreview(false);
    return;
  }
  if (cDirty) scheduleCardPreview();  // 有未保存修改时刷新编辑态预览，避免被已保存内容覆盖
  else cPreviewProject();
};

// ---- 式神头像预览（双式神框单槽位 2 倍渲染）：仅主要式神显示，衍生物式神不显示 ----
function isMainShikigami(card) { return !!card && card.type === '式神' && !card.shikigami; }
const cPortraitImg = document.getElementById('c-portrait');
let cPortraitTimer = null, cPortraitSeq = 0, cPortraitAppliedSeq = 0, cPortraitUrl = null;
async function cPreviewPortrait(withForm) {
  const seq = ++cPortraitSeq;
  if (!curProject || !curCard || !isMainShikigami(formData)) {
    cPortraitAppliedSeq = seq;
    cPortraitImg.style.display = 'none';
    syncSubpreviews();
    return;
  }
  let r;
  try {
    r = await fetch(`/api/projects/${enc(curProject)}/cards/${enc(curCard)}/portrait_preview`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(withForm ? {card: formData} : {})});
  } catch (e) { return; }  // 头像预览失败不抢主预览的错误显示
  if (seq <= cPortraitAppliedSeq) return;
  if (!r.ok) {
    cPortraitAppliedSeq = seq;
    cPortraitImg.style.display = 'none'; syncSubpreviews(); return;
  }
  const blob = await r.blob();
  if (seq <= cPortraitAppliedSeq) return;
  cPortraitAppliedSeq = seq;
  const url = URL.createObjectURL(blob);
  const prev = cPortraitUrl;
  cPortraitUrl = url;
  cPortraitImg.src = url;
  cPortraitImg.style.display = 'block';
  syncSubpreviews();
  if (prev) URL.revokeObjectURL(prev);
}

// ---- 卡图/头像鼠标操作（仅卡牌库 tab 卡牌编辑态；布局 tab 画布交互在 #l-preview 上，不受影响）----
// 左键拖拽=偏移（拖拽方向=图片移动方向）、滚轮=缩放（上滚放大每档 ×1.05，下滚 ÷1.05）、
// 右键按住+滚轮=旋转（每档 ±3°，正角度顺时针，与 artRow 数值口径一致）；
// 数值双向同步右侧输入框（artRow 输入框按 id 回写）；撤回栈与脏标记同 afterEdit 口径，
// 预览按通道合并到动画帧，在途期间只留最新待办、不排队回放；卡图同时刷新主卡与常驻实体，头像只刷新自身
// 机制编辑态（或非式神卡的头像框）不响应；无显式 artwork.path 的缺省图（<id 或卡名>.png）同样可调
const mousePreviewFrames = {art: 0, entity: 0, portrait: 0};
const mousePreviewBusy = {art: false, entity: false, portrait: false};
const mousePreviewQueued = {art: false, entity: false, portrait: false};
function scheduleMousePreview(channel) {
  if (mousePreviewFrames[channel]) return;
  mousePreviewFrames[channel] = requestAnimationFrame(() => {
    mousePreviewFrames[channel] = 0;
    flushMousePreview(channel);
  });
}
function flushMousePreview(channel) {
  if (mousePreviewFrames[channel]) {
    cancelAnimationFrame(mousePreviewFrames[channel]);
    mousePreviewFrames[channel] = 0;
  }
  if (mousePreviewBusy[channel]) {
    mousePreviewQueued[channel] = true;
    return;
  }
  mousePreviewBusy[channel] = true;
  const request = channel === 'art' ? cPreviewForm(false, false)
    : channel === 'entity' ? entityPreview() : cPreviewPortrait(true);
  Promise.resolve(request).catch(e => console.error('鼠标预览失败', e)).finally(() => {
    mousePreviewBusy[channel] = false;
    if (!mousePreviewQueued[channel]) return;
    mousePreviewQueued[channel] = false;
    flushMousePreview(channel);
  });
}
function afterMouseEdit(channel) {
  noteEdit();
  cDirty = true;
  const d = document.getElementById('c-dirty');
  if (d) d.textContent = '● 未保存';
  showFormErrors(validateCardJS(formData));
  const cardPending = cPreviewTimer !== null, entityPending = cEntityTimer !== null;
  if (cardPending) { clearTimeout(cPreviewTimer); cPreviewTimer = null; }
  if (entityPending) { clearTimeout(cEntityTimer); cEntityTimer = null; }
  if (cardPending) {
    scheduleMousePreview('art');
    scheduleMousePreview('entity');
    scheduleMousePreview('portrait');
  }
  if (entityPending) scheduleMousePreview('entity');
  scheduleMousePreview(channel);
  if (channel === 'art') scheduleMousePreview('entity');
}
function ensureArtFirst() {
  // 物化 artwork.images[0] 编辑条目（path 可缺省 = <id 或卡名>.png，缺省图同样吃变换）
  if (!formData.artwork || typeof formData.artwork !== 'object') formData.artwork = {};
  const images = Array.isArray(formData.artwork.images) ? formData.artwork.images : [];
  const first = (images[0] && typeof images[0] === 'object') ? images[0] : {};
  formData.artwork.images = [first, ...images.slice(1)];
  return first;
}
function artMouseChannel(img) {
  if (!formData || curMech) return null;
  const art = formData.artwork && Array.isArray(formData.artwork.images) ? formData.artwork.images[0] : null;
  const isPortrait = img === cPortraitImg;
  if (isPortrait && !isMainShikigami(formData)) return null;
  const get = k => {
    const src = isPortrait
      ? (formData.portrait && typeof formData.portrait === 'object' ? formData.portrait : {})
      : (art || {});
    return src[k] ?? (k === 'scale' ? 1 : 0);
  };
  const set = (k, v) => {
    if (isPortrait) formData.portrait = {...(formData.portrait || {}), [k]: v};
    else ensureArtFirst()[k] = v;
    const inp = document.getElementById(`${isPortrait ? 'portrait' : 'art'}-${k}`);
    if (inp) { inp.value = v; inp._cur = v; }  // 回写输入框（_cur 为手动提交的回退基准）
    afterMouseEdit(isPortrait ? 'portrait' : 'art');
  };
  return {get, set};
}
function bindArtMouse(img) {
  let dragStart = null, dragMoved = false;
  img.addEventListener('mousedown', ev => {
    if (ev.button !== 0) return;
    const ch = artMouseChannel(img);
    if (!ch) return;
    ev.preventDefault();  // 阻止图片原生拖拽/选中
    dragMoved = false;
    dragStart = {x: ev.clientX, y: ev.clientY, ox: ch.get('offset_x'), oy: ch.get('offset_y')};
  });
  window.addEventListener('mousemove', ev => {
    if (!dragStart) return;
    const ch = artMouseChannel(img);
    if (!ch) { dragStart = null; dragMoved = false; return; }
    // 画布属性像素 vs CSS 显示像素换算（图片可能缩放显示）
    const rect = img.getBoundingClientRect();
    const ratio = rect.width > 0 && img.naturalWidth > 0 ? img.naturalWidth / rect.width : 1;
    ch.set('offset_x', Math.round(dragStart.ox + (ev.clientX - dragStart.x) * ratio));
    ch.set('offset_y', Math.round(dragStart.oy + (ev.clientY - dragStart.y) * ratio));
    dragMoved = true;
  });
  window.addEventListener('mouseup', () => {
    if (!dragStart) return;
    const moved = dragMoved;
    dragStart = null;
    dragMoved = false;
    if (!moved) return;
    const channel = img === cPortraitImg ? 'portrait' : 'art';
    flushMousePreview(channel);
    if (channel === 'art') flushMousePreview('entity');
  });
  img.addEventListener('wheel', ev => {
    const ch = artMouseChannel(img);
    if (!ch) return;
    ev.preventDefault();  // 阻止页面滚动
    if (ev.buttons & 2) {  // 右键按住 + 滚轮 = 旋转
      ch.set('rotate', Math.round(ch.get('rotate')) + (ev.deltaY < 0 ? 3 : -3));
    } else {
      const s = ch.get('scale') * (ev.deltaY < 0 ? 1.05 : 1 / 1.05);
      ch.set('scale', Math.round(Math.max(0.01, s) * 1000) / 1000);
    }
  }, {passive: false});
  img.addEventListener('contextmenu', ev => {
    if (artMouseChannel(img)) ev.preventDefault();  // 编辑态下阻止右键菜单（右键留给旋转组合键）
  });
}
bindArtMouse(cPreviewImg);
bindArtMouse(cPortraitImg);

// 使用说明弹窗：开/关（点遮罩空白处同样关闭）
const helpModal = document.getElementById('help-modal');
document.getElementById('c-btn-help').onclick = () => { helpModal.style.display = 'block'; };
document.getElementById('help-close').onclick = () => { helpModal.style.display = 'none'; };
helpModal.onclick = ev => { if (ev.target === helpModal) helpModal.style.display = 'none'; };

// ---- 版本日期与多版本（v1.6.0）：日期输入 + 版本下拉 + 新版本按钮（卡牌/机制共用） ----
function currentVersions() {
  const entries = curMech ? mechs : [...cards.shikigami, ...cards.cards];
  const stem = curMech || curCard;
  const e = entries.find(e => (e.versions || []).some(v => v.stem === stem));
  return e ? e.versions : [];
}
function localToday() {
  const d = new Date();
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
}
function validDateStr(v) {  // 可留空；否则须合法 8 位数字 YYYYMMDD（含 2/30 等真实日期校验）
  if (v === undefined || v === null || v === '') return true;
  if (typeof v !== 'string' || !/^\d{8}$/.test(v)) return false;
  const y = +v.slice(0, 4), m = +v.slice(4, 6), d = +v.slice(6, 8);
  const dt = new Date(y, m - 1, d);
  return dt.getFullYear() === y && dt.getMonth() === m - 1 && dt.getDate() === d;
}
function versionRows(div, data, setDate) {
  const l = document.createElement('label');
  l.textContent = '版本日期 ';
  const i = document.createElement('input');
  i.type = 'text'; i.placeholder = 'YYYYMMDD（留空取今天）'; i.value = data.version_date ?? '';
  i.onchange = () => { i.value = i.value.trim(); setDate(i.value); };
  l.appendChild(i);
  const versions = currentVersions();
  if (versions.length) {  // 版本下拉常驻：切换该条目的日期版本（单版本也可编辑日期后保存）
    const sel = document.createElement('select');
    sel.title = '切换该条目的日期版本';
    for (const v of versions) {
      const op = document.createElement('option');
      op.value = v.stem; op.textContent = v.date || v.stem;
      if (v.stem === (curMech || curCard)) op.selected = true;
      sel.appendChild(op);
    }
    sel.onchange = () => curMech ? selectMech(sel.value) : selectCard(sel.value);
    l.appendChild(sel);
  }
  const nv = document.createElement('button');
  nv.textContent = '新版本';
  nv.style.marginLeft = '6px';
  nv.title = '复制该条目最新版本的全部内容，创建新日期版本';
  nv.onclick = createNewVersion;
  l.appendChild(nv);
  const dv = document.createElement('button');
  dv.textContent = '删除此版本';
  dv.style.marginLeft = '6px';
  dv.onclick = deleteCurrentVersion;
  l.appendChild(dv);
  div.appendChild(l);
  const askSlot = document.createElement('div');
  askSlot.id = 'c-version-ask';
  div.appendChild(askSlot);
}
async function createNewVersion() {
  if (!await confirmDiscard()) return;
  const r = await ask({title: '新版本（复制最新版本的全部内容）', value: localToday(),
    target: 'c-version-ask'});
  if (r === null) return;
  const dateStr = r.text.trim();
  if (!validDateStr(dateStr) || !dateStr) { showFormErrors(['版本日期须为合法 YYYYMMDD（8 位数字）']); return; }
  const isMech = !!curMech, seq = selectSeq;
  const url = isMech ? `/api/mechanisms/${enc(curMech)}/new_version`
    : `/api/projects/${enc(curProject)}/cards/${enc(curCard)}/new_version`;
  const resp = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({date: dateStr})});
  if (!resp.ok) {
    const detail = await parseErrorDetail(resp);
    if (seq === selectSeq) showFormErrors(detail);
    return;
  }
  const res = await resp.json();
  if (seq !== selectSeq) return;
  if (isMech) { mDirty = false; await loadMechs(res.stem); }
  else { cDirty = false; await loadCards(res.stem); }
}
async function deleteCurrentVersion() {
  const isMech = !!curMech, seq = selectSeq;
  const stem = curMech || curCard;
  if (!stem) return;
  if (!confirm(`删除当前版本「${stem}」？（同组其他版本不受影响）`)) return;
  const url = isMech ? `/api/mechanisms/${enc(stem)}`
    : `/api/projects/${enc(curProject)}/cards/${enc(stem)}`;
  const resp = await fetch(url, {method: 'DELETE'});
  if (!resp.ok) {
    const detail = await parseErrorDetail(resp);
    if (seq === selectSeq) showFormErrors(detail);
    return;
  }
  if (seq !== selectSeq) return;
  const remaining = currentVersions().filter(v => v.stem !== stem);
  const next = remaining.length ? remaining[0].stem : null;  // versions 降序，首个=剩余最新版
  if (isMech) {
    mDirty = false;
    await loadMechs(next);  // 被删当前版本自动退出编辑态，剩余最新版被选中
  } else {
    cDirty = false; curCard = null;
    await loadCards(next);
  }
}
async function confirmFallbackNaming() {  // 保存/上传卡图前：id 与版本日期未都填写时提示回退口径
  const data = curMech ? mechForm : formData;
  const missing = [];
  if (!curMech && !(data.id || '').trim()) missing.push('id 未填写：配置文件与卡图将回退按卡名命名');
  if (!(data.version_date || '').trim()) missing.push('版本日期留空：保存时将取当前系统日期');
  if (!missing.length) return true;
  return await sessionConfirm(missing.join('\n') + '\n继续？', 'naming');
}

// ---- 对局式神：独立临时状态，不进入卡牌数据、脏标记或撤回栈 ----
let entityState = null;
function entityEligible(card) {
  return !!card && (card.type === '式神' || card.type === '形态' || card.evolve === true);
}
function makeEntityState(card) {
  const level = Number.isInteger(card.level) && ENTITY_LEVELS.includes(card.level) ? card.level : 1;
  const color = LEVEL_COLOR_VALUES.has(card.level_color) ? card.level_color : 'yellow';
  const base = card.evolve === true
    ? cards.shikigami.find(e => e.name === card.shikigami) || {} : card;
  const nonneg = (source, key) => Number.isInteger(source[key]) && source[key] >= 0 ? source[key] : 0;
  let power = nonneg(base, 'power'), health = nonneg(base, 'health');
  if (card.type === '法术' && card.evolve === true) {
    power = Math.max(0, power + (Number.isInteger(card['power+']) ? card['power+'] : 0));
    health = Math.max(0, health + (Number.isInteger(card['health+']) ? card['health+'] : 0));
  }
  return {level, level_color: color, power, health,
          combat_power: 0, shield: 0, art_scale: 1};
}
function setEntityField(key, value) {
  entityState[key] = value;
  scheduleEntityPreview();
}
function appendEntityForm(div) {
  if (!entityState) entityState = makeEntityState(formData);
  selRowC(div, '等级', ENTITY_LEVELS, entityState.level,
    v => setEntityField('level', parseInt(v, 10)));
  selRowC(div, '勾玉颜色', LEVEL_COLORS.map(([v]) => v), entityState.level_color,
    v => setEntityField('level_color', v), v => LEVEL_COLORS.find(([val]) => val === v)[1]);
  artRow(div, '对局缩放', entityState.art_scale, v => setEntityField('art_scale', v),
    null, null, 0.05, 0.01);
  numRowC(div, '力量', entityState.power, true, v => setEntityField('power', v));
  numRowC(div, '生命', entityState.health, true, v => setEntityField('health', v));
  numRowC(div, '战力/乏力', entityState.combat_power, false, v => setEntityField('combat_power', v));
  numRowC(div, '护甲/破甲', entityState.shield, false, v => setEntityField('shield', v));
  const row = document.createElement('div');
  row.style.marginTop = '10px';
  const exportBtn = document.createElement('button');
  exportBtn.textContent = '导出对局式神';
  exportBtn.onclick = exportEntity;
  row.appendChild(exportBtn); div.appendChild(row);
}

function syncCardFrameButtons() {
  const variant = formData && FRAME_VARIANT_TYPES.has(formData.type)
    ? (formData.frame_variant ?? 'norm') : 'norm';
  document.querySelectorAll('#c-frame-variants .fv').forEach(b => {
    b.classList.toggle('active', b.dataset.fv === variant);
    b.disabled = !formData || (b.dataset.fv !== 'norm' && !FRAME_VARIANT_TYPES.has(formData.type));
  });
}
document.querySelectorAll('#c-frame-variants .fv').forEach(b => b.onclick = () => {
  if (!formData || b.disabled) return;
  if (b.dataset.fv === 'norm') delete formData.frame_variant;
  else formData.frame_variant = b.dataset.fv;
  syncCardFrameButtons();
  afterEdit();
});
syncCardFrameButtons();

// ---- 右栏卡牌表单：按类型动态显隐字段，即时校验 + 防抖预览 ----
function buildForm() {
  if (activeAsk) return;  // 防止键盘/程序化变更绕过点击锁后销毁未完成输入框
  const div = document.getElementById('c-form');
  div.innerHTML = '';
  syncCardFrameButtons();
  if (!formData) { div.textContent = '未选中卡牌'; return; }
  const t = formData.type;
  // 类型创建时定死；id 可留空（上传卡图按 id 命名、留空回退卡名；改 id 不动已有卡图）；
  // 卡名直接编辑（name 字段，文件名 stem 不在 GUI 改）
  infoRow(div, '类型', t);
  textRow(div, 'id（2/6/8位）', formData.id ?? '', v => setOptText('id', v));
  textRow(div, '卡名', formData.name ?? '', v => setField('name', v));
  versionRows(div, formData, v => setField('version_date', v));
  if (t === '式神') {
    if (extOptions.marker) factionRow(div);  // 标记扩展：派系 + 派系样式并排
    else selRowC(div, '派系', FACTIONS, formData.faction ?? '红莲', v => setField('faction', v));
    if (extOptions.marker) levelColorRow(div);  // 标记扩展：式神等级/勾玉颜色
    if (formData.shikigami) {
      infoRow(div, '所属式神', formData.shikigami);  // 衍生物式神
      textRow(div, '子类型', formData.special_type ?? '', v => setOptText('special_type', v));
    }
  } else {
    if (extOptions.marker) levelColorRow(div);  // 标记扩展：等级（含 0=无）+ 勾玉颜色并排
    else selRowC(div, '等级', ['1', '2', '3'], String(formData.level ?? 1), v => setField('level', parseInt(v, 10)));
    selRowC(div, '稀有度', rarityOptions(), formData.rarity ?? '无',
      v => { if (v === '无') delete formData.rarity; else formData.rarity = v; afterEdit(); });
    if (EVOLVE_TYPES.has(t)) {
      checkRowC(div, '觉醒', !!formData.evolve, v => {
        formData.evolve = v;
        if (t === '法术' && !v) { delete formData['power+']; delete formData['health+']; }  // 非觉醒法术不可携带数值
        afterEdit(true);
      });
    }
    if (t === '协战') {  // 协战：shikigami 拆为 shikigami1/shikigami2 两个同构组合框
      shikigamiRow(div, '所属式神1', 'shikigami1');
      shikigamiRow(div, '所属式神2', 'shikigami2');
      // 双式神框：缺省不绘制不写进 yaml（取消勾选删键，口径同框品 norm）
      checkRowC(div, '双式神框', !!formData.duo_frame, v => {
        if (v) formData.duo_frame = true; else delete formData.duo_frame;
        afterEdit();
      });
    } else {
      shikigamiRow(div, '所属式神', 'shikigami');
    }
    textRow(div, '子类型', formData.special_type ?? '', v => setOptText('special_type', v));
  }
  // stat 数值按矩阵（法术仅觉醒；式神/形态/幻境强制非负，滚轮微调同布局页交互）；
  // 标记扩展：数值旁加变色下拉（白/红/绿/紫）
  if (t !== '法术' || !!formData.evolve) {
    const nonneg = NONNEG_TYPES.has(t);
    for (const f of STATS_BY_TYPE[t] || []) {
      numRowC(div, STAT_MATRIX[t][f], formData[f] ?? 0, nonneg, v => setField(f, v),
        extOptions.marker ? statColorSelect(f) : null);
    }
  }
  const l = document.createElement('label');
  l.textContent = '描述 ';
  const ta = document.createElement('textarea');
  ta.value = formData.description ?? '';
  ta.onchange = () => {
    ta.value = ta.value.replace(/\n+/g, '\n').replace(/^\n|\n$/g, '');  // 连续换行合并为一个
    setField('description', ta.value);
  };
  l.appendChild(ta); div.appendChild(l);
  // 卡图上传：单按钮——点击弹文件选择框，选中即上传（直接落盘项目 images/ 并写回
  // yaml，不走保存按钮），成功后刷新预览
  const artLabel = document.createElement('label');
  artLabel.textContent = '卡图 ';
  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = 'image/*';
  fileInput.style.display = 'none';
  const upBtn = document.createElement('button');
  upBtn.textContent = '上传卡图';
  upBtn.onclick = () => fileInput.click();
  fileInput.onchange = async () => {
    if (!curProject || !curCard || askBusy() || storageBusy()) return;
    const f = fileInput.files[0];
    if (!f) return;
    guiDebug('artwork.upload.start', `${f.name} (${f.size} bytes, ${f.type || 'unknown'})`);
    if (!await confirmFallbackNaming()) { fileInput.value = ''; return; }
    const seq = selectSeq, project = curProject, stem = curCard, targetForm = formData;
    const uploadId = formData.id ?? '';
    let resp;
    try {
      resp = await fetch(`/api/projects/${enc(project)}/cards/${enc(stem)}/artwork?filename=${enc(f.name)}&id=${enc(uploadId)}`,
        {method: 'POST', headers: {'Content-Type': 'application/octet-stream'}, body: f});
    } catch (e) {
      if (seq === selectSeq) showFormErrors(['上传请求失败: ' + e]);
      return;
    }
    if (!resp.ok) {
      guiDebug('artwork.upload.failed', `HTTP ${resp.status}`);
      const detail = await parseErrorDetail(resp);
      if (seq === selectSeq) showFormErrors(detail);
      return;
    }
    const res = await resp.json();
    guiDebug('artwork.upload.saved', res.path);
    if (seq !== selectSeq || formData !== targetForm) return;  // 旧上传不得污染新卡/已撤回表单
    // 上传已写盘：把 artwork 路径并进表单数据（不置脏），避免后续保存用旧值覆盖
    ensureArtFirst().path = res.path;
    buildForm();  // 重建表单：立即出现卡图定位输入框（原先仅表单构建时按旧 path 条件渲染）
    if (cDirty) scheduleCardPreview(); else cPreviewProject();
  };
  artLabel.appendChild(fileInput); artLabel.appendChild(upBtn); div.appendChild(artLabel);
  const curArt = formData.artwork && Array.isArray(formData.artwork.images) &&
    formData.artwork.images[0] && formData.artwork.images[0].path;
  const curArtRow = document.createElement('div');
  curArtRow.className = 'readonly';
  curArtRow.id = 'c-cur-art';
  curArtRow.textContent = `当前卡图：${curArt || `（缺省 ${formData.name ?? curCard}.png）`}`;
  div.appendChild(curArtRow);
  // 卡图定位：dx/dy/scale/旋转数字输入（旋转绕图片中心、画布自动扩展；亦可在预览画布上拖拽/滚轮/右键滚轮操作，双向同步），改动走保存按钮；
  // 主要式神每项右侧并排「头像」设置（portrait 段，协战双式神框引用本卡图作头像时使用）
  {
    const artFirst = (formData.artwork && Array.isArray(formData.artwork.images) &&
      formData.artwork.images[0]) || {};
    const setArt = (k, v) => { ensureArtFirst()[k] = v; afterEdit(); };
    const withPortrait = isMainShikigami(formData);
    const port = (withPortrait && formData.portrait && typeof formData.portrait === 'object') ? formData.portrait : {};
    const setPort = (k, v) => { formData.portrait = {...(formData.portrait || {}), [k]: v}; afterEdit(); };
    const pv = k => withPortrait ? (port[k] ?? (k === 'scale' ? 1 : 0)) : null;
    const ps = k => withPortrait ? (v => setPort(k, v)) : null;
    artRow(div, '卡图偏移X', artFirst.offset_x ?? 0, v => setArt('offset_x', v), pv('offset_x'), ps('offset_x'), 1, null, ['art-offset_x', 'portrait-offset_x']);
    artRow(div, '卡图偏移Y', artFirst.offset_y ?? 0, v => setArt('offset_y', v), pv('offset_y'), ps('offset_y'), 1, null, ['art-offset_y', 'portrait-offset_y']);
    artRow(div, '卡图缩放', artFirst.scale ?? 1, v => setArt('scale', v), pv('scale'), ps('scale'), 0.05, 0.01, ['art-scale', 'portrait-scale']);
    artRow(div, '卡图旋转(°)', artFirst.rotate ?? 0, v => setArt('rotate', v), pv('rotate'), ps('rotate'), 5, null, ['art-rotate', 'portrait-rotate']);
  }
  if (isMainShikigami(formData)) {
    // 头像框开关（portrait.frame，缺省画框）：勾选才在头像预览/导出头像中绘制斜方框与派系标
    const pf = (formData.portrait && typeof formData.portrait === 'object') ? formData.portrait.frame : undefined;
    checkRowC(div, '头像框', pf !== false, v => {
      const p = {...(formData.portrait || {})};
      if (v) delete p.frame; else p.frame = false;  // 缺省 true 不写进 yaml
      if (Object.keys(p).length) formData.portrait = p; else delete formData.portrait;
      afterEdit();
    });
  }
  if (extOptions.layout) {
    // 单卡布局覆盖：进入布局 tab 的单卡模式（调整结果存卡面 layout 段，仅与全局不同的键写盘）
    const lrow = document.createElement('div');
    lrow.style.marginTop = '10px';
    const lb = document.createElement('button');
    lb.textContent = '调整单卡元素布局';
    lb.onclick = enterCardLayout;
    lrow.appendChild(lb);
    div.appendChild(lrow);
  }
  // 撤回：对鼠标操作与输入框编辑都生效（爆发合并快照，见 noteEdit）
  const urow = document.createElement('div');
  urow.style.marginTop = '10px';
  const ua = document.createElement('button');
  ua.textContent = '撤回全部修改';
  ua.onclick = undoAll;
  const ul = document.createElement('button');
  ul.textContent = '撤回上次修改';
  ul.style.marginLeft = '6px';
  ul.onclick = undoLast;
  urow.appendChild(ua); urow.appendChild(ul);
  div.appendChild(urow);
  const row = document.createElement('div');
  row.style.marginTop = '10px';
  const btn = document.createElement('button');
  btn.textContent = '保存';
  btn.onclick = saveCard;
  const expBtn = document.createElement('button');
  expBtn.textContent = '导出卡图';
  expBtn.style.marginLeft = '6px';
  expBtn.onclick = openExport;
  row.appendChild(btn); row.appendChild(expBtn);
  if (isMainShikigami(formData)) {
    const expP = document.createElement('button');
    expP.textContent = '导出头像';
    expP.style.marginLeft = '6px';
    expP.onclick = exportPortrait;
    row.appendChild(expP);
  }
  const dirty = document.createElement('span');
  dirty.id = 'c-dirty';
  dirty.textContent = cDirty ? '● 未保存' : '';
  row.appendChild(dirty);
  div.appendChild(row);
  if (entityEligible(formData)) appendEntityForm(div);
  const errs = document.createElement('div');
  errs.id = 'c-form-errors';
  div.appendChild(errs);
  showFormErrors(validateCardJS(formData));
}
function infoRow(div, label, val) {
  const d = document.createElement('div');
  d.className = 'readonly';
  d.textContent = `${label}：${val}`;
  div.appendChild(d);
}
function setField(k, v) { formData[k] = v; afterEdit(); }
function setOptText(k, v) {  // 可选字符串字段：清空即删键（不给服务端送空串）
  if (v === '') delete formData[k]; else formData[k] = v;
  afterEdit();
}
// 所属式神组合框：下拉（「（手动填写）」+ 当前项目式神名列表）+ 手动文本框。
// 当前值不在式神列表时下拉显示「（手动填写）」；清空文本删键（setOptText 口径）
function shikigamiRow(div, label, field) {
  const MANUAL = '（手动填写）';
  const names = shikigamiNames();
  const cur = typeof formData[field] === 'string' ? formData[field] : '';
  const manual = cur === '' || !names.includes(cur);
  const l = document.createElement('label');
  l.textContent = label + ' ';
  const s = document.createElement('select');
  for (const o of [MANUAL, ...names]) {
    const op = document.createElement('option');
    op.value = op.textContent = o;
    if (manual ? o === MANUAL : o === cur) op.selected = true;
    s.appendChild(op);
  }
  const i = document.createElement('input');
  i.type = 'text'; i.placeholder = '式神名'; i.value = manual ? cur : '';
  i.style.display = manual ? '' : 'none';
  s.onchange = () => {
    if (s.value === MANUAL) {
      i.value = typeof formData[field] === 'string' ? formData[field] : '';
      i.style.display = ''; i.focus();
    } else {
      i.style.display = 'none';
      setOptText(field, s.value);
    }
  };
  i.onchange = () => { if (s.value === MANUAL) setOptText(field, i.value.trim()); };
  l.appendChild(s); l.appendChild(i); div.appendChild(l);
}
function afterEdit(rebuild = false) {
  noteEdit();
  cDirty = true;
  if (rebuild) buildForm();  // evolve 切换影响 stat 输入区显隐，整表重建
  else {
    const d = document.getElementById('c-dirty');
    if (d) d.textContent = '● 未保存';
    showFormErrors(validateCardJS(formData));
  }
  scheduleCardPreview();
}
function numRowC(div, label, val, nonneg, set, extra = null, max = null, min = null) {
  const l = document.createElement('label');
  l.textContent = label + ' ';
  const i = document.createElement('input');
  i.type = 'number'; i.value = val;
  if (nonneg) i.min = min ?? 0;
  else if (min !== null) i.min = min;
  let cur = val;
  const commit = () => {
    let v = parseInt(i.value, 10);
    if (isNaN(v)) { i.value = cur; return; }
    if (min !== null) v = Math.max(min, v);
    else if (nonneg) v = Math.max(0, v);
    if (max !== null) v = Math.max(-max, Math.min(max, v));
    i.value = v; cur = v; set(v);
  };
  i.onchange = commit;
  i.onwheel = ev => {  // 滚轮微调
    ev.preventDefault();
    i.value = (parseInt(i.value, 10) || 0) + (ev.deltaY < 0 ? 1 : -1);
    commit();
  };
  l.appendChild(i);
  if (extra) { l.appendChild(document.createTextNode(' ')); l.appendChild(extra); }
  div.appendChild(l);
}
// 数值变色下拉（标记扩展）：<field>_color 缺省白不写进 yaml
function statColorSelect(field) {
  const s = document.createElement('select');
  const cur = formData[`${field}_color`] ?? 'white';
  for (const [v, zh] of STAT_VALUE_COLORS) {
    const op = document.createElement('option');
    op.value = v; op.textContent = zh;
    if (v === cur) op.selected = true;
    s.appendChild(op);
  }
  s.onchange = () => {
    if (s.value === 'white') delete formData[`${field}_color`];
    else formData[`${field}_color`] = s.value;
    afterEdit();
  };
  return s;
}
function artRow(div, label, val, set, pval, pset, step = 1, min = null, ids = null) {
  // 卡图 offset/scale 输入：浮点、无滚轮微调（画布上的拖拽/滚轮鼠标操作按 ids 回写这些输入框）；
  // pset 非空（式神卡）时右侧并排一个头像设置输入（portrait 段）
  const l = document.createElement('label');
  l.textContent = label + ' ';
  const mk = (v, st, id) => {
    const i = document.createElement('input');
    if (id) i.id = id;
    i.type = 'number'; i.value = v; i.step = step;
    if (min !== null) i.min = min;
    i._cur = v;  // 手动提交的回退基准（画布鼠标操作回写时同步更新）
    i.onchange = () => {
      let nv = parseFloat(i.value);
      if (isNaN(nv) || (min !== null && nv < min)) { i.value = i._cur; return; }
      i.value = nv; i._cur = nv; st(nv);
    };
    return i;
  };
  l.appendChild(mk(val, set, ids && ids[0]));
  if (pset) {
    l.appendChild(document.createTextNode(' 头像 '));
    l.appendChild(mk(pval, pset, ids && ids[1]));
  }
  div.appendChild(l);
}
function selRowC(div, label, opts, val, set, map = null) {
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
  s.onchange = () => set(s.value);
  l.appendChild(s); div.appendChild(l);
}
function checkRowC(div, label, val, set) {
  const l = document.createElement('label');
  l.textContent = label + ' ';
  const i = document.createElement('input');
  i.type = 'checkbox'; i.checked = val;
  i.onchange = () => set(i.checked);
  l.appendChild(i); div.appendChild(l);
}
// 派系 + 派系样式并排行（标记扩展，式神专用）：样式缺省 2 不写进 yaml
function factionRow(div) {
  const l = document.createElement('label');
  l.textContent = '派系 ';
  const s = document.createElement('select');
  for (const o of FACTIONS) {
    const op = document.createElement('option');
    op.value = op.textContent = o;
    if (o === (formData.faction ?? '红莲')) op.selected = true;
    s.appendChild(op);
  }
  s.onchange = () => setField('faction', s.value);
  const ss = document.createElement('select');
  const curStyle = String(formData.faction_style ?? 2);
  for (const o of FACTION_STYLES) {
    const op = document.createElement('option');
    op.value = op.textContent = String(o);
    if (op.value === curStyle) op.selected = true;
    ss.appendChild(op);
  }
  ss.onchange = () => {
    if (ss.value === '2') delete formData.faction_style;
    else formData.faction_style = parseInt(ss.value, 10);
    afterEdit();
  };
  l.appendChild(s);
  l.appendChild(document.createTextNode(' 派系样式 '));
  l.appendChild(ss); div.appendChild(l);
}
// 等级 + 勾玉颜色并排行（标记扩展）：等级含 0（0=无等级，删 level 键，全类型适用）；
// 勾玉颜色缺省 yellow 不写进 yaml（取消勾选扩展也不回退已选颜色，仅隐藏控件）
function levelColorRow(div) {
  const l = document.createElement('label');
  l.textContent = '等级 ';
  const s = document.createElement('select');
  const cur = String(formData.level ?? 0);
  for (const o of ['0', '1', '2', '3']) {
    const op = document.createElement('option');
    op.value = op.textContent = o;
    if (o === cur) op.selected = true;
    s.appendChild(op);
  }
  s.onchange = () => {
    if (s.value === '0') delete formData.level;
    else formData.level = parseInt(s.value, 10);
    afterEdit();
  };
  const cs = document.createElement('select');
  const curColor = formData.level_color ?? 'yellow';
  for (const [v, zh] of LEVEL_COLORS) {
    const op = document.createElement('option');
    op.value = v; op.textContent = zh;
    if (v === curColor) op.selected = true;
    cs.appendChild(op);
  }
  cs.onchange = () => {
    if (cs.value === 'yellow') delete formData.level_color;
    else formData.level_color = cs.value;
    afterEdit();
  };
  l.appendChild(s);
  l.appendChild(document.createTextNode(' 勾玉颜色 '));
  l.appendChild(cs); div.appendChild(l);
}

// 即时校验：口径对齐 store/schema.py validate_card（artwork 由服务端把最后一道）
function validateCardJS(d) {
  const errors = [];
  const t = d.type;
  if (!TYPES.includes(t)) return [`字段 type：非法卡牌类型「${t}」，须为 ${TYPES.join('/')} 之一`];
  if (typeof d.name !== 'string' || !d.name.trim()) errors.push('字段 name：必填且必须是非空字符串');
  if ('id' in d && typeof d.id !== 'string') errors.push('字段 id：必须是字符串');
  const allowed = new Set(['type', 'name', 'id', 'description', 'artwork', 'level_color', 'layout', 'version_date']);
  if ('version_date' in d && !validDateStr(d.version_date)) errors.push('字段 version_date：必须是合法 YYYYMMDD 日期（8 位数字，可留空）');
  (STATS_BY_TYPE[t] || []).forEach(f => allowed.add(`${f}_color`));  // 数值变色伴随字段
  if (t === '式神') ['faction', 'frame_variant', 'level', 'faction_style', 'portrait', 'shikigami', 'special_type', ...STATS_BY_TYPE['式神']].forEach(f => allowed.add(f));
  else {
    // 协战白名单：shikigami 移除，改为可选 shikigami1/shikigami2（与 store schema 同口径）
    const base = ['level', 'rarity', 'special_type', ...STATS_BY_TYPE[t]];
    if (t === '协战') base.push('shikigami1', 'shikigami2', 'duo_frame');
    else base.push('shikigami');
    base.forEach(f => allowed.add(f));
    if (EVOLVE_TYPES.has(t)) allowed.add('evolve');
    if (FRAME_VARIANT_TYPES.has(t)) allowed.add('frame_variant');  // 协战不可
  }
  for (const k of Object.keys(d)) {
    if (!allowed.has(k)) errors.push(`字段 ${k}：类型「${t}」白名单之外的字段`);
  }
  // 单卡布局覆盖段：形状校验（与服务端 schema 同口径，键名合法性由渲染层兜底）
  if ('layout' in d) {
    const lay = d.layout;
    if (!lay || typeof lay !== 'object' || Array.isArray(lay)) errors.push('字段 layout：必须是映射');
    else for (const [k, sec] of Object.entries(lay)) {
      if (!['elements', 'text_regions'].includes(k)) {
        errors.push(`字段 layout.${k}：未知键（只允许 elements/text_regions）`);
      } else if (!sec || typeof sec !== 'object' || Array.isArray(sec) ||
                 Object.values(sec).some(v => !v || typeof v !== 'object' || Array.isArray(v))) {
        errors.push(`字段 layout.${k}：必须是「名称 → 键值映射」的映射`);
      }
    }
  }
  if (t === '式神') {
    for (const f of ['faction', ...STATS_BY_TYPE['式神']]) {
      if (!(f in d)) errors.push(`缺少必填字段：${f}`);
    }
    if ('faction' in d && !FACTIONS.includes(d.faction)) {
      errors.push(`字段 faction：非法派系「${d.faction}」，须为 ${FACTIONS.join('/')} 之一`);
    }
    if ('faction_style' in d && (!Number.isInteger(d.faction_style) || !FACTION_STYLES.includes(d.faction_style))) {
      errors.push(`字段 faction_style：派系样式必须是整数 ${FACTION_STYLES.join('/')} 之一`);
    }
    for (const f of ['special_type', 'description']) {
      if (f in d && typeof d[f] !== 'string') errors.push(`字段 ${f}：必须是字符串`);
    }
    if ('portrait' in d) {
      if (!d.portrait || typeof d.portrait !== 'object' || Array.isArray(d.portrait)) {
        errors.push('字段 portrait：头像设置必须是映射');
      } else {
        for (const [k, v] of Object.entries(d.portrait)) {
          if (!['offset_x', 'offset_y', 'scale', 'rotate', 'frame'].includes(k)) {
            errors.push(`字段 portrait.${k}：未知键`);
          } else if (k === 'frame') {
            if (typeof v !== 'boolean') errors.push('字段 portrait.frame：必须是布尔值（true/false）');
          } else if (typeof v !== 'number' || !Number.isFinite(v)) {
            errors.push(`字段 portrait.${k}：必须是数字`);
          } else if (k === 'scale' && v <= 0) {
            errors.push('字段 portrait.scale：必须是正数');
          }
        }
      }
    }
  } else {
    // rarity 可缺省（缺省 = 无稀有度，衍生牌口径，与服务端 schema 同口径）
    if ('rarity' in d && !RARITIES.includes(d.rarity)) {
      errors.push(`字段 rarity：非法稀有度「${d.rarity}」，须为 ${RARITIES.join('/')} 之一`);
    }
    if ('evolve' in d && typeof d.evolve !== 'boolean') errors.push('字段 evolve：必须是布尔值（true/false）');
    if ('duo_frame' in d && typeof d.duo_frame !== 'boolean') errors.push('字段 duo_frame：必须是布尔值（true/false）');
    if ('frame_variant' in d && !FRAME_VARIANT_VALUES.has(d.frame_variant)) {
      errors.push(`字段 frame_variant：非法框品「${d.frame_variant}」，须为 ${[...FRAME_VARIANT_VALUES].join('/')} 之一`);
    }
    for (const f of ['shikigami', 'shikigami1', 'shikigami2', 'special_type', 'description']) {
      if (f in d && typeof d[f] !== 'string') errors.push(`字段 ${f}：必须是字符串`);
    }
  }
  if ('level' in d && (!Number.isInteger(d.level) || !LEVELS.includes(d.level))) {
    errors.push(`字段 level：等级必须是整数 ${LEVELS.join('/')} 之一`);
  }
  if ('level_color' in d && !LEVEL_COLOR_VALUES.has(d.level_color)) {
    errors.push(`字段 level_color：非法勾玉颜色「${d.level_color}」，须为 ${[...LEVEL_COLOR_VALUES].join('/')} 之一`);
  }
  for (const f of STATS_BY_TYPE[t]) {
    const cf = `${f}_color`;
    if (cf in d && !STAT_VALUE_COLOR_VALUES.has(d[cf])) {
      errors.push(`字段 ${cf}：非法数值颜色「${d[cf]}」，须为 ${[...STAT_VALUE_COLOR_VALUES].join('/')} 之一`);
    }
  }
  const evolve = !!d.evolve;
  for (const f of STATS_BY_TYPE[t]) {
    if (!(f in d)) continue;
    if (t === '法术' && !evolve) { errors.push(`字段 ${f}：仅觉醒法术牌（evolve: true）可携带数值`); continue; }
    if (!Number.isInteger(d[f])) errors.push(`字段 ${f}：必须是整数`);
    else if (!SIGNED_STATS.includes(f) && d[f] < 0) errors.push(`字段 ${f}：必须是非负整数`);
    else if (Math.abs(d[f]) > 999999999999) errors.push(`字段 ${f}：数值位数不得超过 12 位`);
  }
  // [[关键字]] 括号不校验：未匹配括号按字面文本显示（口径对齐渲染层 parse_keyword_segments）
  return errors;
}

// ---- 保存：422 错误按三结构解析显示在表单侧 ----
async function saveCard() {
  if (askBusy() || storageBusy()) return false;
  guiDebug('save.card.start', curCard || '');
  const errs = validateCardJS(formData);
  if (errs.length) { showFormErrors(errs); return false; }
  if (!await confirmFallbackNaming()) return false;
  const seq = selectSeq, rev = contentRev, project = curProject, stem = curCard;
  const payload = deepCopy(formData);
  let r;
  try {
    r = await fetch(`/api/projects/${enc(project)}/cards/${enc(stem)}`, {method: 'PUT',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
  } catch (e) {
    if (seq === selectSeq) showFormErrors(['保存请求失败: ' + e]);
    return false;
  }
  if (!r.ok) {
    const detail = await parseErrorDetail(r);
    if (seq === selectSeq) showFormErrors(detail);
    return false;
  }
  const res = await r.json();
  if (seq !== selectSeq) return true;  // 已切卡：旧响应不得改写新卡表单/选中态
  if (res.stem) curCard = res.stem;
  cardData = deepCopy(payload);
  if (rev !== contentRev) {  // 保存期间又有编辑：保留新编辑与脏标记，不以旧快照覆盖
    cDirty = true;
    cStatusEl.textContent = '已保存；此后修改仍未保存';
    return true;
  }
  cDirty = false;
  resetUndo();  // 保存后撤回基准=已保存状态，清空撤回栈
  const d = document.getElementById('c-dirty');
  if (d) d.textContent = '';
  showFormErrors([]);
  cStatusEl.textContent = '已保存';
  if (res.updated && res.updated.length) {
    // 式神卡改名：服务端已联动同项目卡的所属式神引用，列表显示名随之刷新
    cStatusEl.textContent = `已保存；已同步更新 ${res.updated.length} 张卡的所属式神引用：${res.updated.join('、')}`;
  }
  // 无 id 卡改名时服务端已重命名配置文件（res.stem 为新文件名）；
  // 总是刷新左侧栏（卡名/文件名变化即时体现）并重新选中当前卡（表单/预览随刷新）
  await loadCards(curCard);
  return true;
}

// ---- 导出：弹窗确认文件名（默认卡名.png），按当前表单内容（含未保存修改）渲染 PNG 并触发浏览器下载 ----
const exportModal = document.getElementById('export-modal');
function openExport() {
  if (!formData || !curProject || !curCard) return;
  const base = String(formData.name || curCard).replace(/[<>:"/\\|?*]/g, '').trim() || 'card';
  document.getElementById('export-name').value = base + '.png';
  document.getElementById('export-error').textContent = '';
  exportModal.style.display = 'block';
}
document.getElementById('export-cancel').onclick = () => { exportModal.style.display = 'none'; };
exportModal.onclick = ev => { if (ev.target === exportModal) exportModal.style.display = 'none'; };
document.getElementById('export-ok').onclick = async () => {
  const errEl = document.getElementById('export-error');
  let fname = document.getElementById('export-name').value.trim();
  if (!fname) { errEl.textContent = '文件名不能为空'; return; }
  if (!/\.png$/i.test(fname)) fname += '.png';
  errEl.textContent = '';
  let r;
  try {
    // 与编辑期预览同口径：项目卡预览 + 表单整体覆盖（含未保存修改与实时卡图定位）；
    // 不传 layout——服务端自动合并卡面 layout 段（单卡布局覆盖）
    r = await fetch(`/api/projects/${enc(curProject)}/cards/${enc(curCard)}/preview`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({card: formData})});
  } catch (e) { errEl.textContent = '导出请求失败: ' + e; return; }
  if (!r.ok) { errEl.textContent = '渲染失败：' + (await parseErrorDetail(r)).join('\n'); return; }
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fname;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
  exportModal.style.display = 'none';
};

async function exportEntity() {
  if (!formData || !curProject || !curCard || !entityEligible(formData)) return;
  if (!entityState) entityState = makeEntityState(formData);
  const errEl = document.getElementById('c-form-errors');
  const base = String(formData.name || curCard).replace(/[<>:"/\\|?*]/g, '').trim() || 'card';
  let r;
  try {
    r = await fetch('/api/entity-preview', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({project: curProject, card: formData, state: entityState})});
  } catch (e) { errEl.textContent = '导出对局式神请求失败: ' + e; return; }
  if (!r.ok) { errEl.textContent = '导出对局式神失败：' + (await parseErrorDetail(r)).join('\n'); return; }
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = base + '_对局.png';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

// ---- 导出头像：按当前头像预览（含头像框开关与未保存 portrait 修改）直接下载 PNG ----
async function exportPortrait() {
  if (!curProject || !curCard || !isMainShikigami(formData)) return;
  const errEl = document.getElementById('c-form-errors');
  const base = String(formData.name || curCard).replace(/[<>:"/\\|?*]/g, '').trim() || 'card';
  let r;
  try {
    r = await fetch(`/api/projects/${enc(curProject)}/cards/${enc(curCard)}/portrait_preview`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({card: formData})});
  } catch (e) { errEl.textContent = '导出头像请求失败: ' + e; return; }
  if (!r.ok) { errEl.textContent = '导出头像失败：' + (await parseErrorDetail(r)).join('\n'); return; }
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = base + '_头像.png';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
