// ================= 独立对局预览 tab（全部状态临时，不写盘、不置脏） =================
let battleStyle = null;
let battleCardState = null;
let battleEntityState = null;
let battleActive = false;
let battleSession = 0;
let battlePreviewTimer = null;
let battlePreviewSeq = 0;
let battlePreviewAppliedSeq = 0;
let battlePreviewUrl = null;
let battleExporting = false;

function battleStyles(card) {
  if (!card) return [];
  if (card.type === '式神') return ['entity'];
  return card.type === '形态' || card.evolve === true ? ['card', 'entity'] : ['card'];
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
  const state = {level, level_color: color, power, health,
    combat_power: 0, shield: 0, energy: null, countdown: null,
    defeated_countdown: null, art_scale: 1};
  for (const field of ['power', 'health', 'combat_power', 'shield']) {
    const key = `${field}_color`;
    state[key] = STAT_VALUE_COLOR_VALUES.has(card[key]) ? card[key] : null;
  }
  return state;
}

function setBattleCardField(key, value) {
  if (!battleCardState) return;
  battleCardState[key] = value;
  scheduleBattlePreview();
}

function setBattleEntityField(key, value) {
  if (!battleEntityState) return;
  battleEntityState[key] = value;
  scheduleBattlePreview();
}

function enterBattlePreview() {
  battleActive = true;
  battleSession++;
  battlePreviewSeq++;
  battlePreviewAppliedSeq = battlePreviewSeq;
  clearTimeout(battlePreviewTimer);
  battlePreviewTimer = null;
  document.getElementById('b-error').textContent = '';
  document.getElementById('b-status').textContent = '';
  if (!formData || !curProject || !curCard || curMech) {
    battleStyle = null;
    battleCardState = null;
    battleEntityState = null;
    document.getElementById('b-status').textContent = '请先在卡牌库选择卡牌';
    buildBattleStyles();
    buildBattleForm();
    document.getElementById('b-btn-export').disabled = true;
    return;
  }
  battleCardState = deepCopy(formData);
  battleCardState.level = Number.isInteger(formData.level) && ENTITY_LEVELS.includes(formData.level)
    ? formData.level : 1;
  battleCardState.level_color = LEVEL_COLOR_VALUES.has(formData.level_color)
    ? formData.level_color : 'yellow';
  battleCardState.burst = Number.isInteger(formData.burst) ? formData.burst : 0;
  battleEntityState = battleStyles(formData).includes('entity') ? makeEntityState(formData) : null;
  battleStyle = battleStyles(formData)[0];
  document.getElementById('b-btn-export').disabled = false;
  buildBattleStyles();
  buildBattleForm();
  scheduleBattlePreview();
}

function leaveBattlePreview() {
  battleActive = false;
  battleSession++;
  clearTimeout(battlePreviewTimer);
  battlePreviewTimer = null;
  battlePreviewSeq++;
  battlePreviewAppliedSeq = battlePreviewSeq;
  battleStyle = null;
  battleCardState = null;
  battleEntityState = null;
  battleExporting = false;
  const img = document.getElementById('b-preview');
  img.removeAttribute('src');
  if (battlePreviewUrl) {
    URL.revokeObjectURL(battlePreviewUrl);
    battlePreviewUrl = null;
  }
  document.getElementById('b-error').textContent = '';
  document.getElementById('b-status').textContent = '';
  document.getElementById('b-btn-export').disabled = true;
}

function buildBattleStyles() {
  const div = document.getElementById('b-styles');
  div.innerHTML = '';
  for (const style of battleStyles(battleCardState)) {
    const button = document.createElement('button');
    button.textContent = style === 'card' ? '大卡' : '对局式神';
    button.classList.toggle('active', battleStyle === style);
    button.onclick = () => {
      if (!battleActive || battleStyle === style) return;
      battleStyle = style;
      document.getElementById('b-error').textContent = '';
      buildBattleStyles();
      buildBattleForm();
      scheduleBattlePreview();
    };
    div.appendChild(button);
  }
}

function battleSelectRow(div, label, options, value, set) {
  const row = document.createElement('label');
  row.textContent = label + ' ';
  const select = document.createElement('select');
  for (const [option, text] of options) {
    const el = document.createElement('option');
    el.value = option;
    el.textContent = text;
    if (option === value) el.selected = true;
    select.appendChild(el);
  }
  select.onchange = () => set(select.value);
  row.appendChild(select);
  div.appendChild(row);
  return select;
}

function battleNumberRow(div, label, value, set, min = null, id = null, disabled = false) {
  const row = document.createElement('label');
  row.textContent = label + ' ';
  const input = document.createElement('input');
  input.type = 'number';
  input.value = value;
  input.disabled = disabled;
  if (min !== null) input.min = min;
  if (id) input.id = id;
  let current = value;
  input.onchange = () => {
    const parsed = parseInt(input.value, 10);
    if (!Number.isFinite(parsed) || (min !== null && parsed < min)) {
      input.value = current;
      return;
    }
    current = parsed;
    input.value = parsed;
    set(parsed);
  };
  row.appendChild(input);
  div.appendChild(row);
  return input;
}

function battleScaleRow(div) {
  const row = document.createElement('label');
  row.textContent = '对局缩放 ';
  const input = document.createElement('input');
  input.type = 'number';
  input.step = 0.05;
  input.min = 0.01;
  input.value = battleEntityState.art_scale;
  input.onchange = () => {
    const value = parseFloat(input.value);
    if (!Number.isFinite(value) || value < 0.01) {
      input.value = battleEntityState.art_scale;
      return;
    }
    input.value = value;
    setBattleEntityField('art_scale', value);
  };
  row.appendChild(input);
  div.appendChild(row);
}

function battleColorOptions() {
  return STAT_VALUE_COLORS.map(([value, text]) => [value, text]);
}

function battleColorField(style, field, value) {
  const color = value === 'white' ? null : value;
  if (style === 'card') setBattleCardField(field, color);
  else setBattleEntityField(field, color);
}

function battleCheckbox(div, label, checked, set, disabled = false) {
  const row = document.createElement('label');
  row.className = 'inline';
  row.textContent = label + ' ';
  const input = document.createElement('input');
  input.type = 'checkbox';
  input.checked = checked;
  input.disabled = disabled;
  input.onchange = () => set(input.checked);
  row.appendChild(input);
  div.appendChild(row);
  return input;
}

function battleCounterMode() {
  if (!battleEntityState) return 'none';
  if (battleEntityState.energy !== null) return 'energy';
  if (battleEntityState.countdown !== null) return 'countdown';
  return 'none';
}

function setBattleCounterMode(mode) {
  if (!battleEntityState) return;
  if (mode === 'energy') {
    battleEntityState.energy = Number.isInteger(battleEntityState.energy)
      ? Math.max(0, battleEntityState.energy) : 0;
    battleEntityState.countdown = null;
  } else if (mode === 'countdown') {
    battleEntityState.countdown = Number.isInteger(battleEntityState.countdown)
      ? Math.max(1, battleEntityState.countdown) : 1;
    battleEntityState.energy = null;
  } else {
    battleEntityState.energy = null;
    battleEntityState.countdown = null;
  }
  buildBattleForm();
  scheduleBattlePreview();
}

function setBattleDefeated(enabled) {
  if (!battleEntityState) return;
  battleEntityState.defeated_countdown = enabled ? 3 : null;
  buildBattleForm();
  scheduleBattlePreview();
}

function setBattlePermanent(permanent) {
  if (!battleEntityState || battleEntityState.defeated_countdown === null) return;
  battleEntityState.defeated_countdown = permanent ? 'infinity' : 3;
  buildBattleForm();
  scheduleBattlePreview();
}

function buildBattleForm() {
  const div = document.getElementById('b-form');
  div.innerHTML = '';
  if (!battleStyle || !battleCardState) {
    div.textContent = '请先在卡牌库选择卡牌';
    return;
  }
  const state = battleStyle === 'card' ? battleCardState : battleEntityState;
  const setField = battleStyle === 'card' ? setBattleCardField : setBattleEntityField;
  battleSelectRow(div, '等级', ENTITY_LEVELS.map(v => [String(v), String(v)]), String(state.level),
    value => setField('level', parseInt(value, 10)));
  battleSelectRow(div, '勾玉颜色', LEVEL_COLORS, state.level_color,
    value => setField('level_color', value));
  if (battleStyle === 'card') {
    battleNumberRow(div, '爆能', state.burst, value => setBattleCardField('burst', value));
    for (const field of STATS_BY_TYPE[state.type] || []) {
      const key = `${field}_color`;
      battleSelectRow(div, `${STAT_MATRIX[state.type][field]}颜色`, battleColorOptions(),
        state[key] || 'white', value => battleColorField('card', key, value));
    }
    return;
  }
  battleScaleRow(div);
  for (const [field, label, nonneg] of [
    ['power', '力量', true], ['health', '生命', true],
    ['combat_power', '战力/乏力', false], ['shield', '护甲/破甲', false],
  ]) {
    battleNumberRow(div, label, state[field], value => setBattleEntityField(field, value),
      nonneg ? 0 : null);
    battleSelectRow(div, `${label}颜色`, battleColorOptions(), state[`${field}_color`] || 'white',
      value => battleColorField('entity', `${field}_color`, value));
  }
  const mode = battleCounterMode();
  battleSelectRow(div, '右上状态', [['none', '无'], ['energy', '能量'], ['countdown', '倒计时']],
    mode, setBattleCounterMode);
  if (mode !== 'none') {
    battleNumberRow(div, '右上数值', state[mode], value => setBattleEntityField(mode, value),
      mode === 'energy' ? 0 : 1, 'b-counter-value');
  }
  const defeated = state.defeated_countdown !== null;
  const permanent = state.defeated_countdown === 'infinity';
  battleCheckbox(div, '气绝', defeated, setBattleDefeated);
  battleCheckbox(div, '永久', permanent, setBattlePermanent, !defeated);
  if (defeated) {
    battleNumberRow(div, '气绝倒计时', permanent ? 3 : state.defeated_countdown,
      value => setBattleEntityField('defeated_countdown', value), 1,
      'b-defeated-value', permanent);
  }
}

function scheduleBattlePreview() {
  if (!battleActive) return;
  clearTimeout(battlePreviewTimer);
  battlePreviewTimer = setTimeout(() => {
    battlePreviewTimer = null;
    return battlePreview();
  }, 300);
}

function battleRequest(style, project, stem, card, state) {
  if (style === 'entity') {
    return fetch('/api/entity-preview', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({project, card, state}),
    });
  }
  const renderCard = {...card};
  if (renderCard.level === 0) delete renderCard.level;
  return fetch(`/api/projects/${enc(project)}/cards/${enc(stem)}/preview`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({card: renderCard}),
  });
}

async function handleBattlePreviewResponse(r, seq, session) {
  if (!battleActive || session !== battleSession || seq <= battlePreviewAppliedSeq) return;
  if (!r.ok) {
    const detail = await parseErrorDetail(r);
    if (!battleActive || session !== battleSession || seq <= battlePreviewAppliedSeq) return;
    battlePreviewAppliedSeq = seq;
    document.getElementById('b-error').textContent = '预览失败：' + detail.join('\n');
    return;
  }
  const blob = await r.blob();
  if (!battleActive || session !== battleSession || seq <= battlePreviewAppliedSeq) return;
  battlePreviewAppliedSeq = seq;
  const url = URL.createObjectURL(blob);
  const previous = battlePreviewUrl;
  battlePreviewUrl = url;
  document.getElementById('b-preview').src = url;
  document.getElementById('b-error').textContent = '';
  if (previous) URL.revokeObjectURL(previous);
}

async function battlePreview() {
  if (!battleActive || !battleStyle || !battleCardState) return;
  const seq = ++battlePreviewSeq;
  const session = battleSession;
  const style = battleStyle;
  let response;
  try {
    response = await battleRequest(style, curProject, curCard,
      deepCopy(battleCardState), deepCopy(battleEntityState));
  } catch (e) {
    if (battleActive && session === battleSession && seq > battlePreviewAppliedSeq) {
      battlePreviewAppliedSeq = seq;
      document.getElementById('b-error').textContent = '预览请求失败: ' + e;
    }
    return;
  }
  await handleBattlePreviewResponse(response, seq, session);
}

async function exportBattlePreview() {
  if (!battleActive || battleExporting || !battleStyle || !battleCardState) return false;
  const style = battleStyle;
  const session = battleSession;
  const card = deepCopy(battleCardState);
  const state = deepCopy(battleEntityState);
  const base = String(card.name || curCard).replace(/[<>:"/\\|?*]/g, '').trim() || 'card';
  const button = document.getElementById('b-btn-export');
  const error = document.getElementById('b-error');
  battleExporting = true;
  button.disabled = true;
  error.textContent = '';
  try {
    const response = await battleRequest(style, curProject, curCard, card, state);
    if (!response.ok) {
      const detail = await parseErrorDetail(response);
      if (battleActive && session === battleSession && style === battleStyle) {
        error.textContent = '导出失败：' + detail.join('\n');
      }
      return false;
    }
    const blob = await response.blob();
    if (!battleActive || session !== battleSession || style !== battleStyle) return false;
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = base + (style === 'entity' ? '_对局' : '') + '.png';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    return true;
  } catch (e) {
    if (battleActive && session === battleSession && style === battleStyle) {
      error.textContent = '导出请求失败: ' + e;
    }
    return false;
  } finally {
    if (battleActive && session === battleSession) {
      battleExporting = false;
      button.disabled = false;
    }
  }
}

document.getElementById('b-btn-refresh').onclick = battlePreview;
document.getElementById('b-btn-export').onclick = exportBattlePreview;
