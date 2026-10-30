// ================= 入口 =================
// 「最近更新」弹窗：内容由 /api/version 附带（bwpdiy/changelog.py 按版本维护）；
// 服务每次启动生成 boot_id，与 localStorage 比对——只在服务启动后第一次打开页面时自动弹出
const changelogModal = document.getElementById('changelog-modal');
function openChangelog(version, notes) {
  document.getElementById('changelog-title').textContent = `最近更新（v${version}）`;
  const ul = document.getElementById('changelog-list');
  ul.innerHTML = '';
  for (const n of (notes && notes.length ? notes : ['本版本无更新说明。'])) {
    const li = document.createElement('li');
    li.innerHTML = n;  // 内容为本项目 changelog.py 第一方静态文本（非用户输入），支持 <b> 等行内标签
    ul.appendChild(li);
  }
  changelogModal.style.display = 'block';
}
document.getElementById('c-btn-changelog').onclick = () => {
  fetch('/api/version').then(r => r.json())
    .then(v => openChangelog(v.version, v.notes)).catch(() => {});
};
document.getElementById('changelog-close').onclick = () => { changelogModal.style.display = 'none'; };
changelogModal.onclick = ev => { if (ev.target === changelogModal) changelogModal.style.display = 'none'; };

fetch('/api/version').then(r => r.json()).then(v => {
  document.title += ' v' + v.version;
  document.querySelector('#topnav .brand .ver').textContent = 'v' + v.version;
  if (v.boot_id && localStorage.getItem('bwpdiy_boot_id') !== String(v.boot_id)) {
    localStorage.setItem('bwpdiy_boot_id', v.boot_id);
    openChangelog(v.version, v.notes);
  }
}).catch(() => {});
applyExtOptions();  // 扩展选项恢复（含布局 navtab 显隐）
loadProjects();
bootMechs();  // 机制全局列表（不随项目切换）；启动瞬间服务未就绪时有限重试
// 自动更新检查：有新版出横幅；exe 一键更新（下载后程序退出替换重启），开发模式仅给下载链接
// 页面加载即查一次，此后每 1min 复查（下载/更新进行中暂停复查，避免覆盖进度提示）
let updateApplying = false;
function checkUpdate() {
  if (updateApplying) return;
  fetch('/api/update/check').then(r => r.json()).then(u => {
    if (!u.has_update) return;
    document.getElementById('update-text').textContent = `发现新版本 ${u.latest}（当前 v${u.current}）`;
    const btn = document.getElementById('update-btn');
    if (u.frozen) {
      btn.onclick = async () => {
        if (!confirm(`下载并更新到 ${u.latest}？程序将自动重启。`)) return;
        updateApplying = true;
        btn.disabled = true;
        const textEl = document.getElementById('update-text');
        textEl.textContent = '正在下载更新，请稍候…';
        // 下载进度轮询（1s）：区分「低速下载中」与「真正卡死」，失败原因见运行目录 logs 日志
        const progressTimer = setInterval(() => {
          fetch('/api/update/progress').then(r => r.json()).then(p => {
            if (!p.active) return;
            const mb = p.downloaded / 1e6;
            textEl.textContent = p.total > 0
              ? `正在下载更新：${mb.toFixed(1)} / ${(p.total / 1e6).toFixed(1)} MB（${Math.floor(p.downloaded / p.total * 100)}%），请稍候…`
              : `正在下载更新：已下载 ${mb.toFixed(1)} MB，请稍候…`;
          }).catch(() => {});
        }, 1000);
        let r;
        try {
          r = await fetch('/api/update/apply', {method: 'POST'});
        } catch (e) {
          // 更新成功时进程退出会掐断连接，也可能落到此处：按成功提示处理
          clearInterval(progressTimer);
          textEl.textContent = '程序正在退出并更新重启（若未自动启动请手动打开）';
          return;
        }
        clearInterval(progressTimer);
        if (r.ok) {
          textEl.textContent = '下载完成，程序即将退出并自动更新重启';
        } else {
          textEl.textContent = '更新失败：' + (await parseErrorDetail(r)).join('；')
            + '（可点右侧「前往下载」手动更新；详细原因见运行目录 logs 日志）';
          document.getElementById('update-link').style.display = '';
          btn.disabled = false;
          updateApplying = false;
        }
      };
    } else {
      btn.style.display = 'none';
      document.getElementById('update-link').style.display = '';
    }
    document.getElementById('update-banner').style.display = 'block';
  }).catch(() => {});  // 离线/检查失败静默：不出横幅
}
checkUpdate();
setInterval(checkUpdate, 60000);
if (location.hash === '#layout' && extOptions.layout) showTab('layout');  // /layout 重定向落点（布局 tab 隐藏时不跳转）

function hasUnsavedChanges() { return dirty || singleDirty || cDirty || mDirty; }
async function shutdownTool() {
  if (hasUnsavedChanges() && !await sessionConfirm(
      '有未保存修改，退出将丢失这些修改，继续退出？', 'unsaved')) return;
  const button = document.getElementById('app-shutdown');
  button.disabled = true;
  manualShutdown = true;
  let r;
  try { r = await fetch('/api/shutdown', {method: 'POST'}); }
  catch (e) { r = null; }  // 服务已先退出时同样关闭标签页，且不再弹普通断连提示
  if (r && !r.ok) {
    manualShutdown = false;
    button.disabled = false;
    button.textContent = '退出失败，请重试';
    return;
  }
  window.close();
  button.textContent = '服务已关闭，请关闭标签页';  // 浏览器禁止脚本关窗时的回退提示
}
document.getElementById('app-shutdown').onclick = shutdownTool;

// 未保存修改时关闭或刷新标签页弹浏览器确认框；用户选择本会话免提示后同样跳过
window.addEventListener('beforeunload', ev => {
  if (!manualShutdown && !sessionPromptSuppressed.unsaved && hasUnsavedChanges()) {
    ev.preventDefault(); ev.returnValue = '';
  }
});
