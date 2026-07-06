const API = '';

async function fetchJSON(url, opts = {}) {
    try {
        const resp = await fetch(API + url, opts);
        if (!resp.ok) throw new Error(resp.status + ' ' + resp.statusText);
        return await resp.json();
    } catch (e) {
        console.error('API error:', e);
        return null;
    }
}

async function loadHealth() {
    const h = await fetchJSON('/health');
    if (!h) return;
    document.getElementById('version-badge').textContent = 'v' + h.version;
    const statusClass = h.status === 'healthy' ? 'status-healthy' : 'status-degraded';
    const cpuColor = h.cpu_percent > 80 ? 'var(--error)' : 'var(--accent)';
    const memColor = h.memory_percent > 80 ? 'var(--error)' : 'var(--accent)';
    document.getElementById('health-content').innerHTML = `
        <div class="stat-row"><span class="stat-label">Status</span><span class="stat-value ${statusClass}">${h.status.toUpperCase()}</span></div>
        <div class="stat-row"><span class="stat-label">CPU</span><span class="stat-value">${h.cpu_percent}%</span></div>
        <div class="progress-bar"><div class="progress-fill" style="width:${h.cpu_percent}%;background:${cpuColor}"></div></div>
        <div class="stat-row" style="margin-top:8px"><span class="stat-label">Memory</span><span class="stat-value">${h.memory_percent}%</span></div>
        <div class="progress-bar"><div class="progress-fill" style="width:${h.memory_percent}%;background:${memColor}"></div></div>
        <div class="stat-row" style="margin-top:8px"><span class="stat-label">Engine</span><span class="stat-value">${h.engine_active ? '🟢 Active' : '⚪ Idle'}</span></div>
    `;
}

async function loadAgentStatus() {
    const s = await fetchJSON('/status');
    if (!s) return;
    const running = s.running;
    document.getElementById('agent-content').innerHTML = running ?
        `<div class="stat-row"><span class="stat-label">State</span><span class="status-healthy stat-value">RUNNING</span></div>
         <div class="stat-row"><span class="stat-label">Step</span><span class="stat-value">${s.step}</span></div>
         <div class="stat-row"><span class="stat-label">Max Steps</span><span class="stat-value">${s.max_steps}</span></div>` :
        `<p class="muted">Agent is idle</p>`;
}

async function loadTelemetry() {
    const t = await fetchJSON('/telemetry/summary');
    if (!t) { document.getElementById('telemetry-content').innerHTML = '<p class="muted">Telemetry disabled</p>'; return; }
    const rate = t.actions.success_rate || 0;
    const rateColor = rate > 90 ? 'var(--success)' : rate > 70 ? 'var(--warning)' : 'var(--error)';
    document.getElementById('telemetry-content').innerHTML = `
        <div class="stat-row"><span class="stat-label">Total Runs</span><span class="stat-value">${t.runs.total}</span></div>
        <div class="stat-row"><span class="stat-label">Completed / Failed</span><span class="stat-value"><span class="status-healthy">${t.runs.completed}</span> / <span class="status-error">${t.runs.failed}</span></span></div>
        <div class="stat-row"><span class="stat-label">Avg Steps</span><span class="stat-value">${t.avg_steps}</span></div>
        <div class="stat-row"><span class="stat-label">Actions</span><span class="stat-value">${t.actions.total}</span></div>
        <div class="stat-row"><span class="stat-label">Success Rate</span><span class="stat-value" style="color:${rateColor}">${rate}%</span></div>
        <div class="stat-row"><span class="stat-label">LLM Tokens</span><span class="stat-value">${(t.llm_tokens.input + t.llm_tokens.output).toLocaleString()}</span></div>
    `;
}

async function loadPlugins() {
    const p = await fetchJSON('/plugins');
    if (!p || !p.plugins) { document.getElementById('plugins-content').innerHTML = '<p class="muted">No plugins</p>'; return; }
    const html = p.plugins.map(pl => `
        <div class="plugin-item">
            <div><div class="plugin-name">${pl.name}</div><div class="plugin-desc">${pl.description || ''}</div></div>
            <span class="badge">v${pl.version}</span>
        </div>`).join('');
    document.getElementById('plugins-content').innerHTML = html || '<p class="muted">No plugins loaded</p>';
}

async function loadMarketplace() {
    const m = await fetchJSON('/marketplace/list');
    if (!m || !m.plugins) { document.getElementById('marketplace-content').innerHTML = '<p class="muted">Registry unreachable</p>'; return; }
    const html = m.plugins.map(pl => `
        <div class="marketplace-item">
            <div><div class="plugin-name">${pl.name}</div><div class="plugin-desc">${pl.description || ''}</div></div>
            <button class="btn btn-sm ${pl.installed ? 'btn-success' : ''}" ${pl.installed ? 'disabled' : ''} onclick="installPlugin('${pl.name}')">${pl.installed ? '✓ Installed' : 'Install'}</button>
        </div>`).join('');
    document.getElementById('marketplace-content').innerHTML = html || '<p class="muted">No plugins available</p>';
}

async function installPlugin(name) {
    const r = await fetchJSON('/marketplace/install', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name}) });
    if (r) { loadMarketplace(); loadPlugins(); }
}

async function startGoal() {
    const goal = document.getElementById('goal-input').value;
    if (!goal) return;
    const r = await fetchJSON('/goal', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({goal}) });
    document.getElementById('action-result').textContent = JSON.stringify(r, null, 2);
}

async function stopAgent() {
    const r = await fetchJSON('/stop', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}' });
    document.getElementById('action-result').textContent = JSON.stringify(r, null, 2);
}

async function takeScreenshot() {
    const r = await fetch('/screenshot');
    document.getElementById('action-result').textContent = r.ok ? 'Screenshot captured' : 'Failed: ' + r.status;
}

async function checkUpdate() {
    const u = await fetchJSON('/update-check');
    if (u && u.update_available) {
        alert('Update available! Current: v' + u.current_version + ' → Latest: v' + u.latest_version);
    } else if (u) {
        alert('You are on the latest version (v' + u.current_version + ')');
    }
}

async function loadAll() {
    await Promise.all([loadHealth(), loadAgentStatus(), loadTelemetry(), loadPlugins(), loadMarketplace()]);
}

// Auto-refresh every 10 seconds
loadAll();
setInterval(loadAll, 10000);
