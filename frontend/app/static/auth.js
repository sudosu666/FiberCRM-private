(function () {
  'use strict';

  var TOKEN_KEY = 'fiberops_token';
  var USER_KEY = 'fiberops_user';

  function normalizeRole(role) {
    if (!role) return null;
    if (typeof role === 'string') return role;
    if (typeof role === 'object' && role.value) return role.value;
    return String(role);
  }

  function getStoredToken() {
    return window.localStorage.getItem(TOKEN_KEY);
  }

  function getStoredUser() {
    var raw = window.localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch (_err) {
      return null;
    }
  }

  function getRoles(user) {
    if (!user) return [];
    var roles = [];
    if (Array.isArray(user.roles)) {
      roles = user.roles.map(normalizeRole).filter(Boolean);
    }
    var primary = normalizeRole(user.role);
    if (primary && roles.indexOf(primary) === -1) roles.unshift(primary);
    return roles;
  }

  function saveSession(token, user) {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    if (user) window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  function clearSession() {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(USER_KEY);
  }

  async function fetchJson(url, opts) {
    var options = opts ? Object.assign({}, opts) : {};
    var headers = Object.assign({}, options.headers || {});
    var token = getStoredToken();
    if (token) headers.Authorization = 'Bearer ' + token;
    options.headers = headers;

    var response = await fetch(url, options);
    if (!response.ok) {
      var detail = '';
      try {
        var payload = await response.clone().json();
        if (payload && payload.detail) detail = String(payload.detail);
      } catch (_jsonErr) {
        try {
          detail = (await response.text()).trim();
        } catch (_textErr) {
          detail = '';
        }
      }
      var err = new Error((detail || (response.status + ' ' + url)));
      err.status = response.status;
      err.detail = detail || null;
      throw err;
    }

    if (response.status === 204) return null;
    return response.json();
  }

  async function refreshMe() {
    var token = getStoredToken();
    if (!token) return null;
    try {
      var me = await fetchJson('/auth/me');
      saveSession(token, me);
      return me;
    } catch (_err) {
      clearSession();
      return null;
    }
  }

  function routeForRoles(user) {
    var roles = getRoles(user);
    if (roles.indexOf('Designer') >= 0) return '/designer';
    if (roles.indexOf('ConnectionDispatcher') >= 0) return '/connections-dispatch';
    if (roles.indexOf('Dispatcher') >= 0) return '/dispatcher';
    if (roles.indexOf('Warehouse') >= 0) return '/warehouse';
    if (roles.indexOf('Builder') >= 0 || roles.indexOf('Welder') >= 0 || roles.indexOf('Connector') >= 0) return '/field';
    return '/dispatcher';
  }

  async function requireAuth(config) {
    var cfg = config || {};
    var token = getStoredToken();
    if (!token) {
      throw new Error('unauthorized');
    }

    var user = getStoredUser();
    if (!user) {
      user = await refreshMe();
      if (!user) throw new Error('unauthorized');
    }

    if (Array.isArray(cfg.roles) && cfg.roles.length > 0) {
      var granted = getRoles(user);
      var allowed = cfg.roles.map(normalizeRole);
      var ok = allowed.some(function (role) {
        return granted.indexOf(role) >= 0;
      });
      if (!ok) throw new Error('forbidden-role');
    }

    return user;
  }

  function bindUserBar() {
    var user = getStoredUser();
    var roles = getRoles(user);
    var roleLabel = roles.length ? roles.join(', ') : 'Без авторизації';

    var nameEl = document.getElementById('authUserName');
    if (nameEl) nameEl.textContent = user && user.name ? user.name : 'Гість';

    var roleEl = document.getElementById('authUserRole');
    if (roleEl) roleEl.textContent = roleLabel;

    var loginLink = document.getElementById('authLoginLink');
    var logoutBtn = document.getElementById('authLogoutButton');

    if (loginLink) loginLink.hidden = Boolean(user);
    if (logoutBtn) logoutBtn.hidden = !user;

    if (logoutBtn) {
      logoutBtn.onclick = function () {
        clearSession();
        window.location.href = '/login';
      };
    }
  }

  window.FiberAuth = {
    getStoredToken: getStoredToken,
    getStoredUser: getStoredUser,
    getRoles: getRoles,
    saveSession: saveSession,
    clearSession: clearSession,
    fetchJson: fetchJson,
    refreshMe: refreshMe,
    requireAuth: requireAuth,
    bindUserBar: bindUserBar,
    routeForRoles: routeForRoles
  };
})();
