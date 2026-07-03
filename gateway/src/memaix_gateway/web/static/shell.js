// SPDX-License-Identifier: AGPL-3.0-or-later
// Shell behaviour: sidebar toggle, project picker, user badge, admin link,
// outbox badge (FEATURE-WEB-UI-FOUNDATION.md §4.4). Loaded last on every page.

(() => {
  // --- Sidebar collapse (persisted) -----------------------------------
  if (localStorage.getItem('memaix_sidebar_collapsed') === 'true') {
    document.body.dataset.collapsed = 'true';
  }
  document.getElementById('sidebar-toggle')?.addEventListener('click', () => {
    const collapsed = document.body.dataset.collapsed === 'true';
    document.body.dataset.collapsed = collapsed ? 'false' : 'true';
    localStorage.setItem('memaix_sidebar_collapsed', String(!collapsed));
  });

  // --- Active nav highlight -------------------------------------------
  const path = location.pathname.replace(/\/$/, '') || '/app';
  const page = path === '/app' ? 'home' : path.split('/')[2];
  document.querySelectorAll(`.nav-${page}`).forEach((el) => el.classList.add('active'));

  // --- Project selection ------------------------------------------------
  // URL ?project=X always wins and is written back to localStorage.
  const urlProject = new URLSearchParams(location.search).get('project');
  if (urlProject) localStorage.setItem('memaix_project', urlProject);
  const currentProject = () =>
    new URLSearchParams(location.search).get('project')
      ?? localStorage.getItem('memaix_project') ?? '';

  const pickers = [
    document.getElementById('project-picker'),
    document.getElementById('project-picker-mobile'),
  ].filter(Boolean);

  const onPick = (val) => {
    localStorage.setItem('memaix_project', val);
    location.href = location.pathname + '?project=' + encodeURIComponent(val);
  };
  pickers.forEach((p) => p.addEventListener('change', () => onPick(p.value)));

  // --- Populate from /app/api/me ---------------------------------------
  window.ME = api('GET', '/app/api/me').then((me) => {
    if (!me) return null;
    const project = currentProject() || me.projects[0] || '';
    pickers.forEach((p) => {
      p.textContent = '';
      me.projects.forEach((proj) => {
        const opt = document.createElement('option');
        opt.value = proj;
        opt.textContent = proj;
        if (proj === project) opt.selected = true;
        p.append(opt);
      });
    });
    const role = me.is_admin ? 'admin' : (me.role_map[project] ?? '');
    for (const id of ['user-badge', 'user-badge-mobile']) {
      const badge = document.getElementById(id);
      if (badge) badge.textContent = role ? `${me.user} · ${role}` : me.user;
    }
    document.querySelectorAll('.nav-admin').forEach((el) => { el.hidden = !me.is_admin; });
    return me;
  }).catch(() => null);

  // --- Outbox badge (poll, pauses when tab hidden) ----------------------
  pollBadge('/app/api/me', document.querySelector('.outbox-badge'));

  // --- Logout ------------------------------------------------------------
  document.getElementById('logout-btn')?.addEventListener('click', async () => {
    try { await api('POST', '/board/auth/logout'); } catch { /* best effort */ }
    location.href = '/app';
  });
})();
