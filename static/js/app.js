const API_BASE = window.location.origin + '/api';
let authToken = localStorage.getItem('authToken');

document.addEventListener('DOMContentLoaded', () => {
  if (!authToken) showLoginPage();
  else loadDashboard();
});

function showLoginPage() {
  document.getElementById('root').innerHTML = `
    <div class="login-container">
      <div class="login-box">
        <h1>🔐 Logger</h1>
        <form id="loginForm">
          <div class="form-group">
            <label for="token">Discord Token</label>
            <input type="password" id="token" placeholder="Paste your Discord token" required>
          </div>
          <button type="submit" class="login-btn">Login & Start Logging</button>
        </form>
      </div>
    </div>
  `;
  document.getElementById('loginForm').addEventListener('submit', handleLogin);
}

async function handleLogin(e) {
  e.preventDefault();
  const token = document.getElementById('token').value;
  try {
    const response = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token })
    });
    if (response.ok) {
      authToken = btoa(token);
      localStorage.setItem('authToken', authToken);
      loadDashboard();
    } else alert('Login failed');
  } catch (error) {
    console.error('Login error:', error);
    alert('Error during login');
  }
}

function loadDashboard() {
  document.getElementById('root').innerHTML = `
    <div class="navbar">
      <div class="navbar-brand">🔍 Discord Logger</div>
      <div><button class="btn btn-secondary" onclick="logout()">Logout</button></div>
    </div>
    <div class="container">
      <div id="dashboardContent"></div>
    </div>
  `;
  loadDashboardContent();
}

async function loadDashboardContent() {
  try {
    const dash = await fetch(`${API_BASE}/dashboard`, {
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    if (!dash.ok) throw new Error('Failed to load dashboard');
    const data = await dash.json();
    document.getElementById('dashboardContent').innerHTML = `
      <div class="dashboard-grid">
        <div class="stat-card"><div class="stat-label">Total Users</div><div class="stat-value">${data.total_users}</div></div>
        <div class="stat-card"><div class="stat-label">Total Messages</div><div class="stat-value">${data.total_messages}</div></div>
        <div class="stat-card"><div class="stat-label">Total Servers</div><div class="stat-value">${data.total_servers}</div></div>
        <div class="stat-card"><div class="stat-label">Logged IPs</div><div class="stat-value">${data.logged_ips}</div></div>
      </div>
      <div class="search-section">
        <h2>🔍 Search Users</h2>
        <div class="search-box">
          <input type="text" id="userSearch" placeholder="Search by ID, username...">
          <button class="btn btn-primary" onclick="searchUsers()">Search</button>
        </div>
        <div id="searchResults" class="results-container"></div>
      </div>
    `;
    document.getElementById('userSearch').addEventListener('keypress', (e) => {
      if (e.key === 'Enter') searchUsers();
    });
  } catch (error) {
    console.error('Dashboard error:', error);
  }
}

async function searchUsers() {
  const query = document.getElementById('userSearch').value;
  if (!query) return;
  const div = document.getElementById('searchResults');
  div.innerHTML = '<div class="loading-container"><div class="loader"></div></div>';
  try {
    const res = await fetch(`${API_BASE}/users/search?q=${encodeURIComponent(query)}&limit=50`, {
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    if (!res.ok) throw new Error('Search failed');
    const users = await res.json();
    if (users.length === 0) {
      div.innerHTML = '<p>No users found</p>';
      return;
    }
    div.innerHTML = users.map(user => `
      <div class="user-result" onclick="viewUserDetail('${user.id}')">
        <div><div class="user-name">${user.display_name || user.username}</div><div style="font-size: 0.85rem; color: var(--text-secondary);">ID: ${user.id}</div></div>
      </div>
    `).join('');
  } catch (error) {
    console.error('Search error:', error);
  }
}

async function viewUserDetail(userId) {
  try {
    const res = await fetch(`${API_BASE}/users/${userId}`, {
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    if (!res.ok) throw new Error('Failed to load user');
    const user = await res.json();
    document.getElementById('dashboardContent').innerHTML = `
      <button class="btn btn-secondary" onclick="loadDashboard()" style="margin-bottom: 1rem;">← Back</button>
      <div style="background: rgba(26, 31, 58, 0.6); border: 1px solid var(--border); padding: 2rem; border-radius: 8px;">
        <h2 style="color: var(--accent); margin-bottom: 1rem;">${user.display_name || user.username}</h2>
        <p><strong>ID:</strong> ${user.id}</p>
        <p><strong>Username:</strong> @${user.username}</p>
        <p><strong>Bio:</strong> ${user.bio || 'N/A'}</p>
        <p><strong>Messages:</strong> ${user.message_count}</p>
        <p><strong>Servers:</strong> ${user.server_count}</p>
        <div class="tabs">
          <div class="tab active" onclick="switchTab(event, 'messages')">Messages</div>
          <div class="tab" onclick="switchTab(event, 'history')">History</div>
        </div>
        <div id="messages" class="tab-content active">
          <div style="display: flex; gap: 1rem; margin-bottom: 1rem;">
            <input type="text" class="filter-input" id="keywordFilter" placeholder="Search by keyword...">
            <button class="btn btn-primary" onclick="loadUserMessages('${userId}')">Search</button>
          </div>
          <div id="messagesContainer"></div>
        </div>
        <div id="history" class="tab-content">
          <h3 style="color: var(--accent); margin-bottom: 1rem;">Name History</h3>
          <div id="nameHistory"></div>
          <h3 style="color: var(--accent); margin-top: 2rem; margin-bottom: 1rem;">Avatar History</h3>
          <div id="avatarHistory"></div>
        </div>
      </div>
    `;
    loadUserMessages(userId);
    loadNameHistory(user);
    loadAvatarHistory(user);
  } catch (error) {
    console.error('Load user error:', error);
  }
}

async function loadUserMessages(userId) {
  const keyword = document.getElementById('keywordFilter')?.value || '';
  const div = document.getElementById('messagesContainer');
  div.innerHTML = '<div class="loading-container"><div class="loader"></div></div>';
  try {
    const url = new URL(`${API_BASE}/users/${userId}/messages`, window.location.origin);
    if (keyword) url.searchParams.append('keyword', keyword);
    const res = await fetch(url, {
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    if (!res.ok) throw new Error('Failed to load messages');
    const data = await res.json();
    if (data.messages.length === 0) {
      div.innerHTML = '<p>No messages found</p>';
      return;
    }
    div.innerHTML = data.messages.map(msg => `
      <div class="message-item">
        <div style="color: var(--text-secondary); margin-bottom: 0.5rem;">${new Date(msg.created_at).toLocaleString()}</div>
        <div>${escapeHtml(msg.content)}</div>
      </div>
    `).join('');
  } catch (error) {
    console.error('Load messages error:', error);
  }
}

function loadNameHistory(user) {
  const div = document.getElementById('nameHistory');
  if (user.name_history.length === 0) {
    div.innerHTML = '<p>No name changes</p>';
    return;
  }
  div.innerHTML = user.name_history.map(entry => `
    <div class="message-item"><div style="color: var(--text-secondary);">${new Date(entry.changed_at).toLocaleString()}</div><strong>${entry.name}</strong></div>
  `).join('');
}

function loadAvatarHistory(user) {
  const div = document.getElementById('avatarHistory');
  if (user.avatar_history.length === 0) {
    div.innerHTML = '<p>No avatar changes</p>';
    return;
  }
  div.innerHTML = user.avatar_history.map(entry => `
    <div class="message-item"><div style="color: var(--text-secondary);">${new Date(entry.changed_at).toLocaleString()}</div><img src="${entry.url}" style="width: 50px; height: 50px; border-radius: 4px; margin-top: 0.5rem;"></div>
  `).join('');
}

function switchTab(event, tabName) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  event.target.classList.add('active');
  document.getElementById(tabName).classList.add('active');
}

function logout() {
  localStorage.removeItem('authToken');
  authToken = null;
  showLoginPage();
}

function escapeHtml(text) {
  const map = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'};
  return text.replace(/[&<>"']/g, m => map[m]);
}
