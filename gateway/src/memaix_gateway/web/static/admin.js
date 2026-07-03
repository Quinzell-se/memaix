// SPDX-License-Identifier: AGPL-3.0-or-later
// Admin read views: users / projects / audit / system
// (FEATURE-WEB-UI-OUTBOX-AND-ADMIN.md §1.3). All tables are DOM-built.

(async () => {
  const me = await window.ME;
  if (!me) return;
  if (!me.is_admin) {
    document.getElementById('admin-denied').hidden = false;
    document.getElementById('admin-tabs').hidden = true;
    document.querySelectorAll('.admin-pane').forEach((p) => { p.hidden = true; });
    return;
  }

  const panes = ['users', 'projects', 'audit', 'system'];
  document.querySelectorAll('#admin-tabs .tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('#admin-tabs .tab').forEach((x) => x.classList.remove('tab-active'));
      tab.classList.add('tab-active');
      panes.forEach((p) => {
        document.getElementById(`admin-${p}`).hidden = p !== tab.dataset.tab;
      });
    });
  });

  const table = (headers, rows) => {
    const tbl = document.createElement('table');
    tbl.className = 'admin-table';
    const thead = document.createElement('thead');
    const tr = document.createElement('tr');
    headers.forEach((h) => { const th = document.createElement('th'); th.textContent = h; tr.append(th); });
    thead.append(tr);
    const tbody = document.createElement('tbody');
    rows.forEach((cells) => {
      const trb = document.createElement('tr');
      cells.forEach((c) => {
        const td = document.createElement('td');
        if (c instanceof Node) td.append(c); else td.textContent = String(c);
        trb.append(td);
      });
      tbody.append(trb);
    });
    tbl.append(thead, tbody);
    return tbl;
  };

  const roleChips = (grants) => {
    const span = document.createElement('span');
    span.textContent = Object.entries(grants).map(([p, r]) => `${p}:${r}`).join('  ') || '—';
    return span;
  };

  // --- Users -------------------------------------------------------------
  try {
    const users = await api('GET', '/app/api/admin/users');
    const rows = users.map((u) => [
      u.id,
      u.admin ? '🛡' : '',
      u.disabled ? t('web_admin_disabled') : '',
      roleChips(u.grants),
    ]);
    document.getElementById('admin-users').append(
      table([t('web_admin_user'), 'Admin', 'Status', t('web_admin_grants')], rows));
  } catch (e) { toast(e.message, 'error'); }

  // --- Projects ----------------------------------------------------------
  try {
    const projects = await api('GET', '/app/api/admin/projects');
    const rows = projects.map((p) => [
      p.name, p.allow_send ? '✓' : '✗', p.outbox, p.users,
      p.vault.length > 40 ? '…' + p.vault.slice(-38) : p.vault,
    ]);
    document.getElementById('admin-projects').append(
      table([t('web_admin_project'), 'allow_send', 'outbox', t('web_admin_users'), 'vault'], rows));
  } catch (e) { toast(e.message, 'error'); }

  // --- Audit ---------------------------------------------------------------
  const tbody = document.getElementById('audit-tbody');
  const moreBtn = document.getElementById('audit-more');
  let offset = 0;

  const auditRow = (entry) => {
    const tr = document.createElement('tr');
    if (!entry.ok) tr.className = 'audit-row-error';
    [relTime(entry.ts), entry.user, entry.project, entry.tool,
     entry.ok ? '✓' : '✗', entry.detail ?? ''].forEach((c) => {
      const td = document.createElement('td');
      td.textContent = String(c);
      tr.append(td);
    });
    return tr;
  };

  const loadAudit = async (reset) => {
    if (reset) { offset = 0; tbody.textContent = ''; }
    const params = new URLSearchParams();
    const userF = document.getElementById('audit-user').value.trim();
    const projF = document.getElementById('audit-project').value.trim();
    const toolF = document.getElementById('audit-tool').value.trim();
    const okF = document.getElementById('audit-ok').value;
    const sinceF = document.getElementById('audit-since').value;
    if (userF) params.set('user', userF);
    if (projF) params.set('project', projF);
    if (toolF) params.set('tool', toolF);
    if (okF) params.set('ok', okF);
    if (sinceF) params.set('since', sinceF);
    params.set('offset', String(offset));
    params.set('limit', '50');
    try {
      const data = await api('GET', `/app/api/admin/audit?${params}`);
      data.entries.forEach((e) => tbody.append(auditRow(e)));
      offset += data.entries.length;
      moreBtn.hidden = !data.has_more;
    } catch (e) { toast(e.message, 'error'); }
  };

  document.getElementById('audit-filter').addEventListener('submit', (e) => {
    e.preventDefault();
    loadAudit(true);
  });
  moreBtn.addEventListener('click', () => loadAudit(false));
  loadAudit(true);

  // --- System ---------------------------------------------------------------
  try {
    const sys = await api('GET', '/app/api/admin/system');
    const statusMark = { PASS: '✅', WARN: '⚠️', FAIL: '❌', SKIP: '⏭' };
    const rows = sys.checks.map((c) => [statusMark[c.status] ?? c.status, c.name, c.message]);
    document.getElementById('admin-system').append(
      table(['', t('web_admin_check'), t('web_admin_detail')], rows));
  } catch (e) { toast(e.message, 'error'); }
})();
