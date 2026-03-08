'use strict';

const FiberAuth = (() => {
  const TOKEN_KEY = 'fiberops_token';
  const USER_KEY = 'fiberops_user';

  function getToken() {
    return window.localStorage.getItem(TOKEN_KEY);
  }

  function setToken(token) {
    window.localStorage.setItem(TOKEN_KEY, token);
  }

  function clear() {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(USER_KEY);
  }

  function getStoredUser() {
    const raw = window.localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }

  function setStoredUser(user) {
    window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  function getAuthHeaders(extra = {}) {
    const token = getToken();
    return token ? { ...extra, Authorization: `Bearer ${token}` } : extra;
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: getAuthHeaders(options.headers || {}),
    });
    if (response.status === 401) {
      clear();
    }
    if (!response.ok) {
      const text = await response.text();
      const error = new Error(`${response.status} ${url} ${text}`);
      error.status = response.status;
      throw error;
    }
    return response.json();
  }

  async function login(phone, password) {
    const response = await fetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone, password }),
    });
    if (!response.ok) {
      const text = await response.text();
      const error = new Error(`${response.status} /auth/login ${text}`);
      error.status = response.status;
      throw error;
    }
    const token = await response.json();
    setToken(token.access_token);
    const user = await fetchJson('/auth/me');
    setStoredUser(user);
    return user;
  }

  async function loadCurrentUser() {
    const token = getToken();
    if (!token) return null;
    try {
      const user = await fetchJson('/auth/me');
      setStoredUser(user);
      return user;
    } catch (error) {
      if (error.status === 401) {
        clear();
        return null;
      }
      throw error;
    }
  }

  function routeForRoles(user) {
    const roles = new Set((user?.roles || []).map((role) => String(role)));
    if (roles.has('ConnectionDispatcher')) return '/connections-dispatch';
    if (roles.has('Dispatcher')) return '/dispatcher';
    if (roles.has('Designer')) return '/designer';
    if (roles.has('Warehouse')) return '/warehouse';
    if (roles.has('Builder') || roles.has('Welder') || roles.has('Connector')) return '/field';
    return '/dispatcher';
  }

  async function requireAuth(options = {}) {
    const user = await loadCurrentUser();
    if (!user) {
      const next = encodeURIComponent(window.location.pathname);
      window.location.href = `/login?next=${next}`;
      return null;
    }
    if (Array.isArray(options.roles) && options.roles.length) {
      const allowed = new Set(options.roles);
      const actual = new Set((user.roles || []).map((role) => String(role)));
      if (![...allowed].some((role) => actual.has(role))) {
        throw new Error('forbidden-role');
      }
    }
    return user;
  }

  function bindUserBar(options = {}) {
    const nameEl = document.getElementById(options.nameId || 'authUserName');
    const roleEl = document.getElementById(options.roleId || 'authUserRole');
    const loginEl = document.getElementById(options.loginId || 'authLoginLink');
    const logoutEl = document.getElementById(options.logoutId || 'authLogoutButton');
    const user = getStoredUser();
    if (nameEl) nameEl.textContent = user?.name || 'Гість';
    if (roleEl) roleEl.textContent = user?.roles?.join(' / ') || 'Без авторизації';
    if (loginEl) loginEl.hidden = Boolean(user);
    if (logoutEl) {
      logoutEl.hidden = !user;
      logoutEl.onclick = () => {
        clear();
        window.location.href = '/login';
      };
    }
  }

  return {
    clear,
    fetchJson,
    getAuthHeaders,
    getStoredUser,
    login,
    loadCurrentUser,
    requireAuth,
    routeForRoles,
    bindUserBar,
  };
})();
