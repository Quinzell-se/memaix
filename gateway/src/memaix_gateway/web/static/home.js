// SPDX-License-Identifier: AGPL-3.0-or-later
// Home dashboard: to-do card, project grid, activity feed
// (FEATURE-WEB-UI-FOUNDATION.md §4.5). All DOM built with createElement.

(async () => {
  const me = await window.ME;
  if (!me) return;

  // --- To do card -------------------------------------------------------
  const todo = document.getElementById('todo-list');
  const addTodo = (label, href, btnLabel) => {
    const li = document.createElement('li');
    const span = document.createElement('span');
    span.textContent = label;
    const a = document.createElement('a');
    a.className = 'btn';
    a.href = href;
    a.textContent = btnLabel;
    li.append(span, a);
    todo.append(li);
  };
  if (me.pending_outbox > 0) {
    addTodo(`${me.pending_outbox} ${t('web_todo_outbox')}`, '/app/outbox', t('web_todo_outbox_go'));
  }
  for (const provider of me.needs_relink) {
    addTodo(`${provider}: ${t('web_todo_relink')}`, '/app/settings#accounts', t('web_todo_relink_go'));
  }
  if (me.onboarding_missing) {
    addTodo(t('web_todo_onboarding'), '/app/settings', t('web_todo_onboarding_go'));
  }
  document.getElementById('todo-empty').hidden = todo.children.length > 0;

  // --- Project grid -------------------------------------------------------
  const grid = document.getElementById('projects-grid');
  for (const project of me.projects) {
    const card = document.createElement('div');
    card.className = 'card project-card';

    const h3 = document.createElement('h3');
    h3.textContent = project;

    const chip = document.createElement('span');
    const role = me.is_admin ? 'admin' : (me.role_map[project] ?? '');
    chip.className = `role-chip role-${role}`;
    chip.textContent = role;

    const count = document.createElement('div');
    count.className = 'muted';
    const spin = document.createElement('span');
    spin.className = 'spinner';
    count.append(spin);

    const open = document.createElement('a');
    open.href = '/app/board?project=' + encodeURIComponent(project);
    open.textContent = t('web_open_board') + ' →';

    card.append(h3, chip, count, open);
    grid.append(card);

    // Card count fetched lazily per project.
    api('GET', '/board/api/board?project=' + encodeURIComponent(project))
      .then((b) => { count.textContent = `${b.total_cards} ${t('web_cards')}`; })
      .catch(() => { count.textContent = ''; });
  }

  // --- Activity feed ------------------------------------------------------
  const feed = document.getElementById('activity-feed');
  try {
    const data = await api('GET', '/board/api/activity');
    const events = (data.events ?? []).slice(-20).reverse();
    if (!events.length) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.textContent = t('web_activity_empty');
      feed.append(empty);
    }
    for (const ev of events) {
      const row = document.createElement('div');
      row.className = 'act-row';
      const mark = document.createElement('span');
      mark.className = ev.ok ? 'act-ok' : 'act-fail';
      mark.textContent = ev.ok ? '✓' : '✗';
      const text = document.createElement('span');
      text.textContent = `${ev.tool} · ${ev.project} · ${relTime(ev.ts)}`;
      row.append(mark, text);
      feed.append(row);
      if (ev.detail) {
        const detail = document.createElement('div');
        detail.className = 'mono muted act-detail';
        detail.textContent = ev.detail;
        feed.append(detail);
      }
    }
  } catch { /* activity unavailable — dashboard still renders */ }
})();
