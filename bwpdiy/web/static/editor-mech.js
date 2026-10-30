// ================= 机制（灵咒/关键字/加护蚀印描述框） =================
// 全局共享池（/api/mechanisms，不随项目切换）；选中机制与选中卡牌互斥，
// 右栏表单/中央预览/脏标记守卫复用卡牌同套设施（c-form / c-preview / cPreviewSeq / c-dirty 栏位）
const MECH_FRAMES = [["invocation", "灵咒"], ["skill", "关键字"], ["seal", "加护蚀印"]];
const MECH_BADGES = [["", "无"], ["bless", "加护"], ["eclipse", "蚀印"]];

function buildMechList() {
  const div = document.getElementById('c-mechs');
  div.innerHTML = '';
  for (const m of mechs) {
    const d = entryItem(m, curMech);  // 机制无 id：仅名称 + 右侧 (版本数)
    d.onclick = () => selectMech(m.stem);
    div.appendChild(d);
  }
  fitListHeight(div);
  syncDeleteButtons();
}
async function loadMechs(selectName = null, reportError = true) {
  let r;
  try { r = await fetch('/api/mechanisms'); }
  catch (e) { if (reportError) listErr(['机制列表请求失败: ' + e]); return false; }
  if (!r.ok) {
    const errors = await parseErrorDetail(r);
    if (reportError) listErr(errors);
    return false;
  }
  mechs = await r.json();
  if (curMech && !mechs.some(m => (m.versions || []).some(v => v.stem === curMech))) { exitMech(); clearCard(); }  // 机制已被外部删除：退出编辑态
  buildMechList();
  if (selectName && mechs.some(m => (m.versions || []).some(v => v.stem === selectName))) await selectMech(selectName, true);
  return true;
}
async function bootMechs(attempt = 0) {
  if (await loadMechs(null, attempt >= 3)) return;
  if (attempt < 3) setTimeout(() => bootMechs(attempt + 1), 1000);
}
function exitMech() {  // 离开机制编辑态（脏守卫由调用方先行，见 confirmDiscard）
  curMech = null; mechData = null; mechForm = null; mDirty = false;
  buildMechList();
}
async function selectMech(name, force = false) {
  if (!force && (name === curMech || !await confirmDiscard())) return;
  clearCard();      // 互斥：清卡牌选中与预览/头像
  buildCardList();
  curMech = name;
  buildMechList();
  listErr([]);
  cStatusEl.textContent = '';
  const seq = ++selectSeq;
  let r;
  try { r = await fetch(`/api/mechanisms/${enc(name)}`); }
  catch (e) { if (seq === selectSeq) { exitMech(); clearCard(); listErr(['机制读取请求失败: ' + e]); } return; }
  if (seq !== selectSeq) return;  // 期间又选了别的，丢弃本次慢响应
  if (!r.ok) { exitMech(); clearCard(); listErr(await parseErrorDetail(r)); return; }
  mechData = await r.json();
  mechForm = deepCopy(mechData);
  mDirty = false;
  buildMechForm();
  mechPreview(false);
}

// ---- 机制表单：关键字名 / 框类型 / 每行字数 / 角标（仅 seal 框）/ 描述 ----
function setMechField(k, v) { mechForm[k] = v; afterMechEdit(); }
function afterMechEdit(rebuild = false) {
  contentRev++;
  mDirty = true;
  if (rebuild) buildMechForm();  // 框类型切换影响角标下拉显隐，整表重建
  else {
    const d = document.getElementById('c-dirty');
    if (d) d.textContent = '● 未保存';
    showFormErrors(validateMechJS(mechForm));
  }
  scheduleMechPreview();
}
function buildMechForm() {
  if (activeAsk) return;
  const div = document.getElementById('c-form');
  div.innerHTML = '';
  if (!mechForm) { div.textContent = '未选中机制'; return; }
  textRow(div, '关键字名', mechForm.name ?? '', v => setMechField('name', v));
  versionRows(div, mechForm, v => setMechField('version_date', v));
  selRowC(div, '框类型', MECH_FRAMES.map(([v]) => v), mechForm.frame ?? 'invocation',
    v => { mechForm.frame = v; if (v !== 'seal') mechForm.badge = null; afterMechEdit(true); },
    v => MECH_FRAMES.find(([val]) => val === v)[1]);
  numRowC(div, '每行字数', mechForm.chars_per_line ?? 12, true,
    v => setMechField('chars_per_line', v), null, null, 1);
  if ((mechForm.frame ?? 'invocation') === 'seal') {  // 加护/蚀印角标仅 seal 框可用
    selRowC(div, '角标', MECH_BADGES.map(([v]) => v), mechForm.badge ?? '',
      v => { mechForm.badge = v || null; afterMechEdit(); },
      v => MECH_BADGES.find(([val]) => val === v)[1]);
  }
  const l = document.createElement('label');
  l.textContent = '描述 ';
  const ta = document.createElement('textarea');
  ta.value = mechForm.text ?? '';
  ta.onchange = () => {
    ta.value = ta.value.replace(/\n+/g, '\n').replace(/^\n|\n$/g, '');  // 连续换行合并为一个
    setMechField('text', ta.value);
  };
  l.appendChild(ta); div.appendChild(l);
  const row = document.createElement('div');
  row.style.marginTop = '10px';
  const btn = document.createElement('button');
  btn.textContent = '保存';
  btn.onclick = saveMech;
  const expBtn = document.createElement('button');
  expBtn.textContent = '导出描述框';
  expBtn.style.marginLeft = '6px';
  expBtn.onclick = exportMech;
  row.appendChild(btn); row.appendChild(expBtn);
  const dirty = document.createElement('span');
  dirty.id = 'c-dirty';
  dirty.textContent = mDirty ? '● 未保存' : '';
  row.appendChild(dirty);
  div.appendChild(row);
  const errs = document.createElement('div');
  errs.id = 'c-form-errors';
  div.appendChild(errs);
  showFormErrors(validateMechJS(mechForm));
}

// 即时校验：口径对齐 store/schema.py validate_mechanism
function validateMechJS(d) {
  const errors = [];
  if (typeof d.name !== 'string' || !d.name.trim()) errors.push('字段 name：必填且必须是非空字符串');
  if (!MECH_FRAMES.some(([v]) => v === d.frame)) errors.push(`字段 frame：非法框类型「${d.frame}」`);
  if (d.badge !== null && d.badge !== undefined && !MECH_BADGES.some(([v]) => v && v === d.badge)) {
    errors.push(`字段 badge：非法角标「${d.badge}」`);
  }
  if (d.badge && d.frame !== 'seal') errors.push('字段 badge：仅加护蚀印框可携带角标');
  if (typeof d.text !== 'string') errors.push('字段 text：必须是字符串');
  if ('chars_per_line' in d && (!Number.isInteger(d.chars_per_line) || d.chars_per_line <= 0)) {
    errors.push('字段 chars_per_line：必须是正整数');
  }
  if ('version_date' in d && !validDateStr(d.version_date)) errors.push('字段 version_date：必须是合法 YYYYMMDD 日期（8 位数字，可留空）');
  return errors;
}

// ---- 机制预览：与卡牌共用 c-preview 图、请求序号与 objectURL 管理 ----
function scheduleMechPreview() {
  clearTimeout(cPreviewTimer);
  cPreviewTimer = setTimeout(() => mechPreview(true), 300);
}
async function mechPreview(withForm) {
  if (!curMech) return;
  const data = withForm ? mechForm : mechData;
  if (!data) return;
  if (withForm && validateMechJS(data).length) return;  // 校验未过不刷预览（错误已在表单侧显示）
  const seq = ++cPreviewSeq;
  let r;
  try {
    r = await fetch(`/api/mechanisms/${enc(curMech)}/preview`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({mechanism: data})});
  } catch (e) {
    if (seq === cPreviewSeq) cErrorEl.textContent = '预览请求失败: ' + e;
    return;
  }
  await cHandlePreviewResponse(r, seq);
}

// ---- 机制保存：关键字名即机制名，改名随保存联动（服务端重命名文件，同卡牌口径） ----
async function saveMech() {
  if (askBusy() || storageBusy()) return;
  guiDebug('save.mechanism.start', curMech || '');
  const errs = validateMechJS(mechForm);
  if (errs.length) { showFormErrors(errs); return; }
  if (!await confirmFallbackNaming()) return;
  const seq = selectSeq, rev = contentRev, oldName = curMech;
  const payload = deepCopy(mechForm);
  let r;
  try {
    r = await fetch(`/api/mechanisms/${enc(oldName)}`, {method: 'PUT',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
  } catch (e) {
    if (seq === selectSeq) showFormErrors(['保存请求失败: ' + e]);
    return;
  }
  if (!r.ok) {
    const detail = await parseErrorDetail(r);
    if (seq === selectSeq) showFormErrors(detail);
    return;
  }
  const res = await r.json();
  if (seq !== selectSeq) return;
  if (res.stem) curMech = res.stem;  // 改名已写盘时即使后续有编辑，也须指向新文件
  mechData = deepCopy(payload);
  if (rev !== contentRev) {
    mDirty = true;
    cStatusEl.textContent = '已保存；此后修改仍未保存';
    return;
  }
  mDirty = false;
  cStatusEl.textContent = '已保存';
  await loadMechs(res.stem || oldName);  // 按最终文件名重选（改名/改日期会重命名文件）
}

// ---- 导出描述框：按当前表单内容（含未保存修改）渲染 PNG 直接下载，文件名=关键字名.png ----
async function exportMech() {
  if (!mechForm || !curMech) return;
  const errEl = document.getElementById('c-form-errors');
  const base = String(mechForm.name || curMech).replace(/[<>:"/\\|?*]/g, '').trim() || 'mechanism';
  let r;
  try {
    r = await fetch(`/api/mechanisms/${enc(curMech)}/preview`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({mechanism: mechForm})});
  } catch (e) { errEl.textContent = '导出请求失败: ' + e; return; }
  if (!r.ok) { errEl.textContent = '导出失败：' + (await parseErrorDetail(r)).join('\n'); return; }
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = base + '.png';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

// ---- 机制操作（新建/删除；重命名=右侧名称输入框修改后保存） ----
const MECH_FRAME_BY_LABEL = Object.fromEntries(MECH_FRAMES.map(([v, l]) => [l, v]));
document.getElementById('c-new-mech').onclick = async () => {
  const r = await ask({title: '新机制（名称 + 框体）',
    options: MECH_FRAMES.map(([, l]) => l), selDefault: '关键字',
    target: 'c-ask-mech'});  // 框类型默认关键字框
  if (!r || !r.text) return;
  if (!await confirmDiscard()) return;
  const resp = await fetch('/api/mechanisms', {method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name: r.text,
      frame: MECH_FRAME_BY_LABEL[r.sel] || 'skill', text: '', badge: null, chars_per_line: 12})});
  if (!resp.ok) { listErr(await parseErrorDetail(resp)); return; }
  listErr([]);
  await loadMechs(r.text);
};
document.getElementById('c-del-mech').onclick = async () => {
  if (!curMech) { listErr(['请先选择机制']); return; }
  if (!confirm(`删除机制「${curMech}」？`)) return;
  const resp = await fetch(`/api/mechanisms/${enc(curMech)}`, {method: 'DELETE'});
  if (!resp.ok) { listErr(await parseErrorDetail(resp)); return; }
  exitMech(); clearCard();
  listErr([]);
  await loadMechs();
};
