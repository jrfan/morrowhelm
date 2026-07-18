const state = {
  view: 'home',
  data: null,
  selectedEmployee: 'ceo',
  showAllCompleted: false,
  chatDrafts: {},
  connectionDraft: null,
  editingConnectionId: null,
  openDetails: new Set(),
};

const ICONS = {
  arrowUpRight: '<path d="M7 17 17 7M7 7h10v10" />',
  shieldCheck: '<path d="M12 3 20 7v5c0 5-3.4 8.4-8 10-4.6-1.6-8-5-8-10V7Z" /><path d="m8.5 12 2.2 2.2 4.8-5" />',
  bot: '<rect x="4" y="7" width="16" height="13" rx="3" /><path d="M9 3h6M12 3v4M8 12h.01M16 12h.01M8 16h8" />',
  sparkles: '<path d="m12 3 1.3 3.7L17 8l-3.7 1.3L12 13l-1.3-3.7L7 8l3.7-1.3ZM5 15l.8 2.2L8 18l-2.2.8L5 21l-.8-2.2L2 18l2.2-.8ZM19 14l.8 2.2L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-.8Z" />',
  chevronDown: '<path d="m6 9 6 6 6-6" />',
  fileText: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6M8 13h8M8 17h8M8 9h2" />',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />',
  download: '<path d="M12 3v12M7 10l5 5 5-5M5 21h14" />',
  plus: '<path d="M12 5v14M5 12h14" />',
  plug: '<path d="M12 22v-5M9 8V2M15 8V2M18 8v3a6 6 0 0 1-12 0V8Z" />',
  checkCircle: '<circle cx="12" cy="12" r="9" /><path d="m8 12 2.5 2.5L16 9" />',
  x: '<path d="m6 6 12 12M18 6 6 18" />',
  edit: '<path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z" />',
  trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 15H6L5 6M10 11v5M14 11v5" />',
  logOut: '<path d="M10 17l5-5-5-5M15 12H3M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5" />',
  more: '<circle cx="5" cy="12" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" />',
};

const $ = (selector) => document.querySelector(selector);

function icon(name, className = 'ui-icon') {
  const classes = className === 'ui-icon' ? 'ui-icon' : `ui-icon ${className}`;
  return `<svg class="${classes}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ''}</svg>`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {'Content-Type': 'application/json', ...(options.headers || {})},
    ...options,
  });
  if (response.status === 401) {
    window.location.href = '/login';
    throw new Error('Sign in required');
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || 'Something went wrong');
  }
  if (response.status === 204) return null;
  return response.json();
}

function toast(message, tone = 'default') {
  const item = document.createElement('div');
  item.className = `toast ${tone}`;
  item.setAttribute('role', tone === 'error' ? 'alert' : 'status');
  item.textContent = message;
  $('#toast-region').append(item);
  window.setTimeout(() => item.remove(), 3600);
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
}

function employee(id) {
  return state.data.employees.find((item) => item.id === id) || state.data.employees[0];
}

function initials(name) {
  return String(name || '').split(' ').filter(Boolean).map((part) => part[0]).slice(0, 2).join('');
}

function relativeTime(value) {
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return 'just now';
  const seconds = Math.max(1, Math.floor((Date.now() - timestamp) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function runForEmployee(employeeId) {
  return state.data.agent_runs.find((run) => run.employee_id === employeeId);
}

function runStatus(status) {
  return ({queued: 'Queued', running: 'Working', succeeded: 'Complete', failed: 'Needs attention', timeout: 'Timed out'})[status] || status || 'Ready';
}

function effectiveModeLabel() {
  return state.data.runtime.effective_demo_mode === 'replay' ? 'DEMO REPLAY READY' : 'LIVE CODEX RUNTIME';
}

function workflowStatus(run) {
  if (!run) return {label: 'Ready', tone: 'ready'};
  if (run.status === 'succeeded') return {label: 'Complete', tone: 'complete'};
  if (run.status === 'failed' || run.status === 'timeout') return {label: 'Needs attention', tone: 'attention'};
  return {label: 'Working', tone: 'working'};
}

function detailOpen(key) {
  return state.openDetails.has(key) ? ' open' : '';
}

function sprintWorkflow() {
  const sprint = state.data.sprint;
  if (!sprint) {
    return `<section class="proof-strip"><span class="proof-number">01</span><div><strong>One brief. Six specialized moves.</strong><p>Research, product, growth, finance, and operations work in parallel. A Chief of Staff turns their outputs into one founder decision.</p></div></section>`;
  }
  const runs = sprint.runs || [];
  const stepDefs = [
    ['research', 'Research'], ['product', 'Product'], ['growth', 'Growth'],
    ['finance', 'Finance'], ['ops', 'Operations'], ['synthesis', 'Founder brief'],
  ];
  const steps = stepDefs.map(([id, label], index) => {
    const run = id === 'synthesis' ? sprint.synthesis : runs.find((item) => item.employee_id === id && item.stage === 'work');
    const status = workflowStatus(run);
    return `<div class="workflow-step ${status.tone}"><span class="workflow-index">${String(index + 1).padStart(2, '0')}</span><div><strong>${label}</strong><small>${status.label}</small></div></div>`;
  }).join(`<span class="workflow-arrow" aria-hidden="true">${icon('chevronDown')}</span>`);
  const statusText = sprint.status === 'complete' ? 'Decision brief ready' : sprint.status === 'synthesizing' ? 'Chief of Staff is synthesizing' : `${sprint.specialists_complete}/${sprint.specialist_count} specialists complete`;
  return `<section class="section-block sprint-section"><div class="section-heading"><div><p class="eyebrow">LIVE SPRINT TRACE</p><h3>${statusText}</h3></div><span class="runtime-pill ${sprint.mode}">${sprint.mode === 'replay' ? 'Replay' : 'Live Codex'}</span></div><div class="workflow-track" aria-label="Sprint stages">${steps}</div><p class="swipe-hint">Swipe to inspect all six stages ${icon('arrowUpRight')}</p><p class="tiny-note">The final brief depends on every specialist output. External actions remain behind Founder Gate.</p></section>`;
}

function artifactCard(item, compact = false) {
  const key = `artifact-${item.run_id}-${item.path}`;
  const filename = item.path.split('/').pop();
  return `<details class="artifact-card" data-detail-key="${escapeHtml(key)}"${detailOpen(key)}>
    <summary><span class="artifact-kind">${escapeHtml(item.kind)}</span><div><strong>${escapeHtml(filename)}</strong><small>${escapeHtml(item.employee_role || item.employee_name || 'Agent')} · ${escapeHtml(item.mode === 'replay' ? 'Replay' : item.model)}</small></div>${icon('chevronDown', 'artifact-chevron')}</summary>
    <div class="artifact-content"><p>${escapeHtml(item.preview || 'Artifact is available in the isolated workspace.')}</p>${compact ? `<div class="artifact-actions"><button class="quiet-button" type="button" data-artifact-copy data-run-id="${escapeHtml(item.run_id)}" data-path="${escapeHtml(item.path)}">${icon('copy')} Copy</button><button class="quiet-button" type="button" data-artifact-download data-run-id="${escapeHtml(item.run_id)}" data-path="${escapeHtml(item.path)}">${icon('download')} Download</button></div>` : ''}</div>
  </details>`;
}

function artifactSection() {
  const artifacts = state.data.artifacts || [];
  if (!artifacts.length) return '';
  return `<section class="section-block"><div class="section-heading"><div><p class="eyebrow">INSPECTABLE OUTPUTS</p><h3>What the team made</h3></div><button class="text-button" type="button" data-action="all-artifacts">View all ${artifacts.length}</button></div><div class="artifact-grid">${artifacts.slice(0, 4).map((item) => artifactCard(item, true)).join('')}</div></section>`;
}

function render() {
  if (!state.data) return;
  $('#company-name').textContent = state.data.company.name;
  $('#approval-badge').textContent = state.data.metrics.pending_approvals;
  $('#approval-badge').hidden = !state.data.metrics.pending_approvals;
  document.querySelectorAll('.nav-item').forEach((button) => {
    const active = button.dataset.view === state.view;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  const views = {home: renderHome, chat: renderChat, tasks: renderTasks, approvals: renderApprovals, people: renderPeople};
  $('#view-root').innerHTML = views[state.view]();
  bindViewEvents();
}

function renderHome() {
  const pending = state.data.approvals.find((item) => item.status === 'pending');
  const pendingCount = state.data.metrics.pending_approvals;
  const activity = state.data.activity.slice(0, 3);
  return `
    <section class="hero-panel">
      <div class="hero-copy"><p class="eyebrow">${escapeHtml(state.data.company.name)} · ${effectiveModeLabel()}</p><h2>Make the next<br /><em>clear move.</em></h2><p class="muted">Five specialists work in parallel. A Chief of Staff brings you one decision. You keep the final say.</p><button class="primary-button demo-launch" data-action="demo-launch">Launch a full sprint ${icon('arrowUpRight')}</button></div>
      <div class="helm-orbit" aria-hidden="true"><span>${icon('arrowUpRight')}</span></div>
    </section>
    <section class="metrics-grid" aria-label="Company overview">
      <article class="metric-card"><span class="metric-icon violet">${icon('arrowUpRight')}</span><strong>${state.data.metrics.active_tasks}</strong><small>Active tasks</small></article>
      <article class="metric-card"><span class="metric-icon orange">${icon('shieldCheck')}</span><strong>${state.data.metrics.pending_approvals}</strong><small>Need your say</small></article>
      <article class="metric-card"><span class="metric-icon teal">${icon('bot')}</span><strong>${state.data.metrics.team_online}</strong><small>Agents online</small></article>
    </section>
    ${sprintWorkflow()}
    ${pending ? `<section class="section-block"><div class="section-heading"><div><p class="eyebrow">FOUNDER GATE</p><h3>${pendingCount === 1 ? 'One decision is waiting' : `${pendingCount} decisions are waiting`}</h3></div><button class="text-button" data-go="approvals">View all</button></div>${approvalCard(pending, true)}</section>` : `<section class="empty-card">${icon('checkCircle', 'empty-symbol')}<h3>The helm is clear</h3><p class="muted">Ask an agent to shape the next task whenever you are ready.</p></section>`}
    ${artifactSection()}
    <section class="section-block"><div class="section-heading"><div><p class="eyebrow">RECENT SIGNALS</p><h3>Company pulse</h3></div></div><div class="activity-list">${activity.map((item) => `<div class="activity-row"><span class="activity-dot"></span><div><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.detail)}</p></div><time>${relativeTime(item.created_at)}</time></div>`).join('')}</div></section>`;
}

function renderChat() {
  const selected = employee(state.selectedEmployee);
  const messages = state.data.conversation.filter((message) => message.employee_id === selected.id);
  const latest = runForEmployee(selected.id);
  const draft = state.chatDrafts[selected.id] || '';
  return `<section class="page-heading"><p class="eyebrow">YOUR VIRTUAL COMPANY</p><h2>Talk it through.</h2><p class="muted">Ask one teammate for context, a plan, or a next move.</p></section>
    <div class="employee-strip" aria-label="Choose a teammate">${state.data.employees.map((item) => `<button class="employee-chip ${item.id === state.selectedEmployee ? 'selected' : ''}" data-employee="${item.id}" aria-pressed="${item.id === state.selectedEmployee}"><span class="avatar ${item.accent}">${initials(item.name)}</span><span>${escapeHtml(item.name.split(' ')[0])}</span></button>`).join('')}</div>
    <div class="chat-agent-bar"><span class="avatar ${selected.accent}">${initials(selected.name)}</span><div><strong>${escapeHtml(selected.name)} · ${escapeHtml(selected.role)}</strong><small>${escapeHtml(selected.agent_model || state.data.runtime.codex_model)} · isolated workspace</small></div><span class="run-state ${latest?.status || 'ready'}">${runStatus(latest?.status)}</span></div>
    <section class="chat-thread" aria-label="Conversation with ${escapeHtml(selected.name)}">${messages.length ? messages.map((message) => `<article class="message ${message.speaker === 'founder' ? 'founder' : ''}"><span class="avatar ${message.speaker === 'founder' ? 'founder-avatar' : selected.accent}">${message.speaker === 'founder' ? 'You' : initials(message.name || selected.name)}</span><div class="message-body"><div class="message-meta"><strong>${message.speaker === 'founder' ? 'You' : escapeHtml(message.name || selected.name)}</strong><time>${relativeTime(message.created_at)}</time></div><p>${escapeHtml(message.content)}</p></div></article>`).join('') : `<div class="empty-card compact">${icon('sparkles', 'empty-symbol')}<h3>Start with one clear question</h3><p class="muted">${escapeHtml(selected.name.split(' ')[0])} will answer here and leave an inspectable run.</p></div>`}</section>
    <form id="chat-form" class="composer"><label class="sr-only" for="chat-message">Message ${escapeHtml(selected.name)}</label><textarea id="chat-message" rows="2" maxlength="4000" placeholder="What should ${escapeHtml(selected.name.split(' ')[0])} work on next?">${escapeHtml(draft)}</textarea><button class="primary-button" type="submit">Send ${icon('arrowUpRight')}</button></form>`;
}

function statusLabel(status) {
  return ({queued:'Queued', in_progress:'In progress', waiting_approval:'Needs approval', completed:'Complete', blocked:'Blocked'})[status] || status;
}

function taskCard(task) {
  const key = `task-${task.id}`;
  return `<details class="task-card" data-detail-key="${escapeHtml(key)}"${detailOpen(key)}><summary>
    <div class="task-card-top"><span class="priority ${escapeHtml(task.priority)}">${escapeHtml(task.priority)}</span><span class="task-id">${escapeHtml(task.id.slice(0, 12))}</span></div>
    <h4>${escapeHtml(task.title)}</h4><p class="task-preview">${escapeHtml(task.description || 'No description provided.')}</p>
    <div class="task-owner"><span class="avatar mini ${employee(task.owner_id).accent}">${initials(employee(task.owner_id).name)}</span><span>${escapeHtml(task.owner_name)}</span><time>${relativeTime(task.updated_at)}</time>${icon('chevronDown', 'task-chevron')}</div>
  </summary><div class="task-body"><p>${escapeHtml(task.description || 'No description provided.')}</p><dl><div><dt>Status</dt><dd>${statusLabel(task.status)}</dd></div><div><dt>Created by</dt><dd>${escapeHtml(task.trigger.replaceAll('_', ' '))}</dd></div></dl></div></details>`;
}

function renderTasks() {
  const grouped = ['in_progress', 'waiting_approval', 'queued', 'completed', 'blocked'];
  return `<section class="page-heading split-heading"><div><p class="eyebrow">WORK IN MOTION</p><h2>Tasks</h2></div><button class="secondary-button" data-action="new-task">${icon('plus')} New task</button></section><div class="task-board">${grouped.map((status) => {
    const all = state.data.tasks.filter((task) => task.status === status);
    const visible = status === 'completed' && !state.showAllCompleted ? all.slice(0, 4) : all;
    const more = status === 'completed' && all.length > 4 ? `<button class="quiet-button show-more" type="button" data-action="toggle-completed">${state.showAllCompleted ? 'Show fewer' : `Show all ${all.length}`}</button>` : '';
    return `<section class="task-column"><div class="column-heading"><span class="status-dot ${status}"></span><h3>${statusLabel(status)}</h3><small>${all.length}</small></div>${visible.map(taskCard).join('') || '<div class="column-empty">Nothing here yet.</div>'}${more}</section>`;
  }).join('')}</div>`;
}

function approvalCard(item, featured = false) {
  const hash = item.action_hash ? `${item.action_hash.slice(0, 12)}…` : 'hash unavailable';
  const key = `approval-${item.id}`;
  return `<article class="approval-card ${featured ? 'featured' : ''}" data-approval="${item.id}">
    <div class="approval-top"><span class="risk-pill ${escapeHtml(item.risk)}"><span></span>${escapeHtml(item.risk)} risk</span><time>${relativeTime(item.created_at)}</time></div>
    <h3>${escapeHtml(item.title)}</h3><p class="approval-summary">${escapeHtml(item.summary)}</p>
    <ul class="impact-list">${item.side_effects.map((effect) => `<li>${escapeHtml(effect)}</li>`).join('')}</ul>
    <details class="approval-details" data-detail-key="${escapeHtml(key)}"${detailOpen(key)}><summary>Inspect exact scope ${icon('chevronDown')}</summary><dl><div><dt>Scopes</dt><dd>${item.requested_scopes.map((scope) => `<code>${escapeHtml(scope)}</code>`).join(' ') || 'None'}</dd></div><div><dt>Recipient</dt><dd>${escapeHtml(item.recipient || 'No external recipient')}</dd></div><div><dt>Reversible</dt><dd>${item.reversible ? 'Yes' : 'No — requires your explicit approval'}</dd></div><div><dt>Action hash</dt><dd><code>${hash}</code></dd></div></dl></details>
    <div class="approval-meta"><span>Requested by <strong>${escapeHtml(item.requester_name)}</strong></span>${item.amount ? `<strong>${escapeHtml(item.currency)} ${escapeHtml(item.amount)}</strong>` : '<strong>No spend</strong>'}</div>
    ${item.status === 'pending' ? `<div class="approval-actions"><button class="secondary-button" data-approval-action="reject" data-id="${item.id}">Reject</button><button class="primary-button" data-approval-action="approve" data-id="${item.id}">${icon('shieldCheck')} Review & approve</button></div>` : `<div class="decision-state ${item.status}">${icon('checkCircle')}<span>${item.status === 'approved' ? 'Approved' : 'Rejected'} · receipt recorded<br /><code>${hash}</code></span></div>`}
  </article>`;
}

function renderApprovals() {
  const pending = state.data.approvals.filter((item) => item.status === 'pending');
  const decided = state.data.approvals.filter((item) => item.status !== 'pending');
  return `<section class="page-heading"><p class="eyebrow">FOUNDER GATE</p><h2>Approvals</h2><p class="muted">Only exact, inspectable actions should cross this line.</p></section><div class="approval-list">${pending.map((item) => approvalCard(item, true)).join('') || `<div class="empty-card">${icon('checkCircle', 'empty-symbol')}<h3>Nothing needs your say</h3><p class="muted">New approval requests will appear here with their real-world impact.</p></div>`}${decided.length ? `<div class="section-heading history-heading"><div><p class="eyebrow">DECISION HISTORY</p><h3>Recently decided</h3></div></div>${decided.map((item) => approvalCard(item)).join('')}` : ''}</div>`;
}

function selectedOption(value, current) {
  return value === current ? ' selected' : '';
}

function renderPeople() {
  const editing = state.editingConnectionId ? state.data.connections.find((item) => item.id === state.editingConnectionId) : null;
  const draft = state.connectionDraft || {
    provider: editing?.provider || 'openai-compatible', label: editing?.label || '', base_url: editing?.base_url || '',
    model: editing?.model || '', api_key: '',
  };
  return `<section class="page-heading"><p class="eyebrow">YOUR VIRTUAL COMPANY</p><h2>People</h2><p class="muted">Six Codex CLI employees, each working inside an isolated local workspace.</p></section>
    <div class="people-grid">${state.data.employees.map((item) => { const runs = state.data.agent_runs.filter((run) => run.employee_id === item.id); const latest = runs[0]; return `<article class="person-card"><div class="person-top"><span class="avatar large ${item.accent}">${initials(item.name)}</span><span class="online-state"><span class="online-dot"></span> Online</span></div><h3>${escapeHtml(item.name)}</h3><p class="role">${escapeHtml(item.role)}</p><p>${escapeHtml(item.focus)}</p><div class="agent-badge"><span class="agent-pulse ${latest?.status === 'running' ? 'running' : ''}"></span> Codex CLI · ${escapeHtml(item.agent_model || state.data.runtime.codex_model)}</div>${latest ? `<p class="agent-latest">${escapeHtml(runStatus(latest.status))} · ${escapeHtml(latest.mode === 'replay' ? 'deterministic replay' : 'live workspace')} · ${relativeTime(latest.created_at)}</p>` : ''}<button class="text-button" data-chat-employee="${item.id}">Talk to ${escapeHtml(item.name.split(' ')[0])} ${icon('arrowUpRight')}</button></article>`; }).join('')}</div>
    <section class="section-block connections-block" id="connections"><div class="section-heading"><div><p class="eyebrow">RUNTIME CONNECTIONS</p><h3>Bring your own runtime</h3></div><span class="security-note">${icon('shieldCheck')} Encrypted locally</span></div><p class="muted">Keys stay encrypted in this MorrowHelm instance and never enter browser storage.</p>
      <form id="connection-form" class="connection-form"><div class="form-heading"><strong>${editing ? 'Edit connection' : 'Add a connection'}</strong>${editing ? '<button class="text-button" type="button" data-action="cancel-connection-edit">Cancel</button>' : ''}</div><div class="form-row"><label>Provider<select id="connection-provider"><option value="openai-compatible"${selectedOption('openai-compatible', draft.provider)}>OpenAI-compatible</option><option value="crewai"${selectedOption('crewai', draft.provider)}>CrewAI</option><option value="a2a"${selectedOption('a2a', draft.provider)}>A2A</option><option value="webhook"${selectedOption('webhook', draft.provider)}>Webhook</option></select></label><label>Connection name<input id="connection-label" required maxlength="120" value="${escapeHtml(draft.label)}" placeholder="My agent gateway" /></label></div><label>Base URL<input id="connection-base-url" inputmode="url" value="${escapeHtml(draft.base_url)}" placeholder="http://127.0.0.1:8080" /></label><div class="form-row"><label>Model<input id="connection-model" value="${escapeHtml(draft.model)}" placeholder="Optional" /></label><label>API Key<input id="connection-api-key" type="password" autocomplete="off" value="${escapeHtml(draft.api_key)}" placeholder="${editing?.has_api_key ? 'Leave blank to keep saved key' : 'Stored encrypted locally'}" /></label></div><button class="primary-button" type="submit">${editing ? 'Save changes' : 'Save connection'}</button></form>
      <div class="connection-list">${state.data.connections.map((connection) => `<article class="connection-card"><span class="connection-icon">${icon('plug')}</span><div class="connection-copy"><strong>${escapeHtml(connection.label)}</strong><p>${escapeHtml(connection.provider)}${connection.model ? ` · ${escapeHtml(connection.model)}` : ''}</p><span class="connected-state">${connection.has_api_key ? `${icon('checkCircle')} Key saved ${escapeHtml(connection.key_hint || '')}` : 'No API key'}</span></div><div class="connection-actions"><button class="icon-button small" type="button" data-connection-action="test" data-id="${connection.id}" aria-label="Test ${escapeHtml(connection.label)}">${icon('checkCircle')}</button><button class="icon-button small" type="button" data-connection-action="edit" data-id="${connection.id}" aria-label="Edit ${escapeHtml(connection.label)}">${icon('edit')}</button><button class="icon-button small danger" type="button" data-connection-action="delete" data-id="${connection.id}" aria-label="Delete ${escapeHtml(connection.label)}">${icon('trash')}</button></div></article>`).join('') || '<div class="column-empty">No runtimes connected yet.</div>'}</div>
    </section>
    <section class="session-card"><div><p class="eyebrow">LOCAL SESSION</p><h3>Founder access</h3><p class="muted">Sign out when this device is shared. Local company data remains on your MorrowHelm host.</p></div><button class="secondary-button" type="button" data-action="logout">${icon('logOut')} Sign out</button></section>`;
}

function bindViewEvents() {
  document.querySelectorAll('[data-go]').forEach((button) => button.addEventListener('click', () => navigate(button.dataset.go)));
  document.querySelectorAll('[data-employee]').forEach((button) => button.addEventListener('click', () => {
    captureChatDraft();
    state.selectedEmployee = button.dataset.employee;
    render();
  }));
  document.querySelectorAll('[data-chat-employee]').forEach((button) => button.addEventListener('click', () => {
    state.selectedEmployee = button.dataset.chatEmployee;
    navigate('chat');
  }));
  document.querySelectorAll('[data-approval-action]').forEach((button) => button.addEventListener('click', () => openApprovalDialog(button.dataset.id, button.dataset.approvalAction)));
  document.querySelectorAll('[data-connection-action]').forEach((button) => button.addEventListener('click', () => handleConnectionAction(button.dataset.id, button.dataset.connectionAction)));
  document.querySelectorAll('details[data-detail-key]').forEach((details) => details.addEventListener('toggle', () => {
    if (details.open) state.openDetails.add(details.dataset.detailKey);
    else state.openDetails.delete(details.dataset.detailKey);
  }));
  bindArtifactActions(document);

  const chatForm = $('#chat-form');
  if (chatForm) {
    chatForm.addEventListener('submit', sendChat);
    $('#chat-message').addEventListener('input', captureChatDraft);
  }
  const connectionForm = $('#connection-form');
  if (connectionForm) {
    connectionForm.addEventListener('submit', saveConnectionForm);
    connectionForm.addEventListener('input', captureConnectionDraft);
    connectionForm.addEventListener('change', captureConnectionDraft);
  }
  document.querySelector('[data-action="new-task"]')?.addEventListener('click', openNewTaskDialog);
  document.querySelector('[data-action="demo-launch"]')?.addEventListener('click', launchDemo);
  document.querySelector('[data-action="all-artifacts"]')?.addEventListener('click', openArtifactsDialog);
  document.querySelector('[data-action="toggle-completed"]')?.addEventListener('click', () => { state.showAllCompleted = !state.showAllCompleted; render(); });
  document.querySelector('[data-action="cancel-connection-edit"]')?.addEventListener('click', () => { state.editingConnectionId = null; state.connectionDraft = null; render(); });
  document.querySelector('[data-action="logout"]')?.addEventListener('click', openLogoutDialog);
}

function navigate(view, {focus = true} = {}) {
  captureChatDraft();
  captureConnectionDraft();
  state.view = view;
  render();
  window.scrollTo({top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
  if (focus) $('#view-root').focus({preventScroll: true});
}

function captureChatDraft() {
  const input = $('#chat-message');
  if (input) state.chatDrafts[state.selectedEmployee] = input.value;
}

function captureConnectionDraft() {
  const form = $('#connection-form');
  if (!form) return;
  state.connectionDraft = {
    provider: $('#connection-provider').value,
    label: $('#connection-label').value,
    base_url: $('#connection-base-url').value,
    model: $('#connection-model').value,
    api_key: $('#connection-api-key').value,
  };
}

function mountDialog({kicker, title, body, primaryLabel = '', primaryTone = '', size = '', onSubmit = null}) {
  const dialog = $('#app-dialog');
  const opener = document.activeElement;
  dialog.className = `app-dialog ${size}`.trim();
  dialog.innerHTML = `<form id="dialog-form"><div class="dialog-header"><div><p class="eyebrow">${escapeHtml(kicker)}</p><h2 id="dialog-title">${escapeHtml(title)}</h2></div><button class="icon-button" type="button" data-dialog-close aria-label="Close dialog">${icon('x')}</button></div><div class="dialog-body">${body}</div><div class="dialog-actions"><button class="secondary-button" type="button" data-dialog-close>Cancel</button>${primaryLabel ? `<button class="primary-button ${primaryTone}" type="submit">${escapeHtml(primaryLabel)}</button>` : '<button class="primary-button" type="button" data-dialog-close>Done</button>'}</div></form>`;
  dialog.querySelectorAll('[data-dialog-close]').forEach((button) => button.addEventListener('click', () => dialog.close()));
  dialog.addEventListener('click', (event) => { if (event.target === dialog) dialog.close(); }, {once: true});
  dialog.addEventListener('close', () => opener?.focus?.(), {once: true});
  const form = $('#dialog-form');
  if (onSubmit) form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
      await onSubmit(new FormData(form));
      dialog.close();
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      button.disabled = false;
    }
  });
  dialog.showModal();
  window.setTimeout(() => dialog.querySelector('[autofocus], input, textarea, select, button')?.focus(), 0);
  return dialog;
}

function openNewTaskDialog() {
  const ownerOptions = state.data.employees.map((item) => `<option value="${item.id}">${escapeHtml(item.name)} · ${escapeHtml(item.role)}</option>`).join('');
  mountDialog({
    kicker: 'NEW COMPANY TASK', title: 'Make the next move concrete', primaryLabel: 'Create task',
    body: `<div class="dialog-fields"><label>Task title<input name="title" required maxlength="200" autofocus placeholder="What needs to happen?" /></label><label>Description<textarea name="description" rows="4" maxlength="4000" placeholder="Add context, constraints, or a definition of done."></textarea></label><div class="form-row"><label>Owner<select name="owner_id">${ownerOptions}</select></label><label>Priority<select name="priority"><option value="medium">Medium</option><option value="high">High</option><option value="low">Low</option></select></label></div></div>`,
    onSubmit: async (formData) => {
      await api('/api/tasks', {method: 'POST', body: JSON.stringify(Object.fromEntries(formData))});
      toast('Task created and queued');
      await refresh();
    },
  });
}

function approvalDialogBody(item, action) {
  const impact = item.side_effects.map((effect) => `<li>${escapeHtml(effect)}</li>`).join('');
  const exact = `<div class="decision-review"><span class="risk-pill ${escapeHtml(item.risk)}"><span></span>${escapeHtml(item.risk)} risk</span><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.summary)}</p><ul class="impact-list">${impact}</ul><dl><div><dt>Scopes</dt><dd>${item.requested_scopes.map((scope) => `<code>${escapeHtml(scope)}</code>`).join(' ') || 'None'}</dd></div><div><dt>Spend</dt><dd>${item.amount ? `${escapeHtml(item.currency)} ${escapeHtml(item.amount)}` : 'No spend'}</dd></div><div><dt>Action hash</dt><dd><code>${escapeHtml(item.action_hash)}</code></dd></div></dl></div>`;
  if (action === 'reject') return `${exact}<label class="dialog-note">What should the team change?<textarea name="note" required rows="3" maxlength="2000" autofocus placeholder="Give the team a clear revision direction."></textarea></label>`;
  return `<p class="dialog-warning">You are approving this exact external action. Any later change to its scope or hash will require a new approval.</p>${exact}`;
}

function openApprovalDialog(id, action) {
  const item = state.data.approvals.find((approval) => approval.id === id);
  if (!item) return;
  mountDialog({
    kicker: action === 'approve' ? 'FINAL FOUNDER CHECK' : 'SEND BACK WITH CONTEXT',
    title: action === 'approve' ? 'Approve this exact action?' : 'Reject and redirect the team',
    primaryLabel: action === 'approve' ? 'Approve exact action' : 'Reject with feedback',
    primaryTone: action === 'reject' ? 'danger-button' : '',
    body: approvalDialogBody(item, action),
    onSubmit: async (formData) => {
      const note = String(formData.get('note') || '');
      await api(`/api/approvals/${id}/decision`, {method: 'POST', body: JSON.stringify({decision: action === 'approve' ? 'approved' : 'rejected', note, expected_version: item.version})});
      toast(action === 'approve' ? 'Approved · execution receipt queued' : 'Rejected · feedback sent');
      await refresh();
    },
  });
}

async function openArtifactsDialog() {
  try {
    const artifacts = await api('/api/artifacts?limit=100');
    const body = artifacts.length ? `<div class="artifact-dialog-grid">${artifacts.map((item) => artifactCard(item, true)).join('')}</div>` : '<div class="column-empty">No artifacts yet.</div>';
    const dialog = mountDialog({kicker: 'INSPECTABLE OUTPUTS', title: `All artifacts · ${artifacts.length}`, body, size: 'wide'});
    bindArtifactActions(dialog);
    dialog.querySelectorAll('details[data-detail-key]').forEach((details) => details.addEventListener('toggle', () => {
      if (details.open) state.openDetails.add(details.dataset.detailKey);
      else state.openDetails.delete(details.dataset.detailKey);
    }));
  } catch (error) {
    toast(error.message, 'error');
  }
}

function bindArtifactActions(root) {
  root.querySelectorAll('[data-artifact-copy]').forEach((button) => button.addEventListener('click', () => copyArtifact(button.dataset.runId, button.dataset.path)));
  root.querySelectorAll('[data-artifact-download]').forEach((button) => button.addEventListener('click', () => downloadArtifact(button.dataset.runId, button.dataset.path)));
}

async function copyArtifact(runId, path) {
  try {
    const artifact = await api(`/api/artifacts/${encodeURIComponent(runId)}/content?path=${encodeURIComponent(path)}`);
    await navigator.clipboard.writeText(artifact.content);
    toast('Artifact copied to clipboard');
  } catch (error) {
    toast(error.message, 'error');
  }
}

function downloadArtifact(runId, path) {
  const link = document.createElement('a');
  link.href = `/api/artifacts/${encodeURIComponent(runId)}/download?path=${encodeURIComponent(path)}`;
  link.download = path.split('/').pop();
  document.body.append(link);
  link.click();
  link.remove();
}

async function sendChat(event) {
  event.preventDefault();
  const input = $('#chat-message');
  const message = input.value.trim();
  if (!message) return;
  const button = event.submitter || event.currentTarget.querySelector('button[type="submit"]');
  button.disabled = true;
  try {
    await api('/api/chat', {method: 'POST', body: JSON.stringify({message, employee_id: state.selectedEmployee})});
    state.chatDrafts[state.selectedEmployee] = '';
    toast(`Message sent to ${employee(state.selectedEmployee).name.split(' ')[0]}`);
    await refresh();
    window.setTimeout(() => window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'}), 0);
  } catch (error) {
    toast(error.message, 'error');
  } finally {
    button.disabled = false;
  }
}

async function launchDemo(event) {
  event.preventDefault();
  const button = event.currentTarget;
  button.disabled = true;
  try {
    await api('/api/demo/launch', {method: 'POST', body: JSON.stringify({prompt: 'Prepare a two-week launch sprint for LumenDesk, a calm planning tool for solo consultants.'})});
    toast('Sprint started · five specialists are moving in parallel');
    state.view = 'home';
    await refresh();
  } catch (error) {
    toast(error.message, 'error');
  } finally {
    button.disabled = false;
  }
}

async function saveConnectionForm(event) {
  event.preventDefault();
  captureConnectionDraft();
  const button = event.currentTarget.querySelector('button[type="submit"]');
  button.disabled = true;
  const payload = {
    provider: state.connectionDraft.provider,
    label: state.connectionDraft.label.trim(),
    base_url: state.connectionDraft.base_url.trim() || null,
    model: state.connectionDraft.model.trim() || null,
    api_key: state.connectionDraft.api_key || null,
  };
  const path = state.editingConnectionId ? `/api/connections/${state.editingConnectionId}` : '/api/connections';
  const method = state.editingConnectionId ? 'PUT' : 'POST';
  try {
    await api(path, {method, body: JSON.stringify(payload)});
    toast(state.editingConnectionId ? 'Connection updated' : 'Connection saved locally');
    state.editingConnectionId = null;
    state.connectionDraft = null;
    await refresh();
  } catch (error) {
    toast(error.message, 'error');
  } finally {
    button.disabled = false;
  }
}

function handleConnectionAction(id, action) {
  const connection = state.data.connections.find((item) => item.id === id);
  if (!connection) return;
  if (action === 'edit') {
    state.editingConnectionId = id;
    state.connectionDraft = {provider: connection.provider, label: connection.label, base_url: connection.base_url || '', model: connection.model || '', api_key: ''};
    render();
    window.setTimeout(() => { $('#connections')?.scrollIntoView({behavior: 'smooth'}); $('#connection-label')?.focus(); }, 0);
    return;
  }
  if (action === 'test') {
    testConnection(connection);
    return;
  }
  if (action === 'delete') openDeleteConnectionDialog(connection);
}

async function testConnection(connection) {
  toast(`Testing ${connection.label}…`);
  try {
    const result = await api(`/api/connections/${connection.id}/test`, {method: 'POST'});
    toast(result.message, result.ok ? 'success' : 'error');
  } catch (error) {
    toast(error.message, 'error');
  }
}

function openDeleteConnectionDialog(connection) {
  mountDialog({
    kicker: 'REMOVE RUNTIME', title: `Delete ${connection.label}?`, primaryLabel: 'Delete connection', primaryTone: 'danger-button',
    body: `<p class="dialog-warning">This removes the connection configuration and its encrypted API key from this local MorrowHelm instance. Agent workspaces and past artifacts are not deleted.</p>`,
    onSubmit: async () => {
      await api(`/api/connections/${connection.id}`, {method: 'DELETE'});
      if (state.editingConnectionId === connection.id) { state.editingConnectionId = null; state.connectionDraft = null; }
      toast('Connection and encrypted key deleted');
      await refresh();
    },
  });
}

function openLogoutDialog() {
  mountDialog({
    kicker: 'LOCAL SESSION', title: 'Sign out of this device?', primaryLabel: 'Sign out',
    body: '<p class="dialog-warning">Your local company data and Agent workspaces remain on the MorrowHelm host. This browser session will be closed.</p>',
    onSubmit: async () => {
      await api('/api/session', {method: 'DELETE'});
      navigator.serviceWorker?.controller?.postMessage({type: 'CLEAR_PRIVATE_CACHE'});
      window.location.href = '/login';
    },
  });
}

async function refresh({background = false} = {}) {
  const next = await api('/api/bootstrap');
  state.data = next;
  const active = document.activeElement;
  const editing = active && ['INPUT', 'TEXTAREA', 'SELECT'].includes(active.tagName);
  if (!background || (!editing && !$('#app-dialog')?.open)) render();
}

document.querySelectorAll('.nav-item').forEach((button) => button.addEventListener('click', () => navigate(button.dataset.view)));
$('#settings-button').addEventListener('click', () => {
  state.view = 'people';
  render();
  window.setTimeout(() => $('#connections')?.scrollIntoView({behavior: 'smooth'}), 0);
});

(async function boot() {
  try {
    await refresh();
  } catch (error) {
    if (error.message !== 'Sign in required') toast(error.message, 'error');
  }
})();

window.setInterval(() => {
  if (state.data && document.visibilityState === 'visible' && navigator.onLine) refresh({background: true}).catch(() => {});
}, 7000);

window.addEventListener('offline', () => toast('You are offline · reconnect to your MorrowHelm host', 'error'));
window.addEventListener('online', () => { toast('Back online · refreshing company state', 'success'); refresh().catch(() => {}); });

if ('serviceWorker' in navigator) navigator.serviceWorker.register('/static/sw.js').catch(() => {});
