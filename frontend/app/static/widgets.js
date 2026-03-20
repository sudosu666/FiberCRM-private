(function () {
  'use strict';

  function endpointBase(context, id) {
    if (context === 'task') return '/api/tasks/' + id;
    if (context === 'building') return '/api/buildings/' + id;
    return '/api/subscriber-requests/' + id;
  }

  function escapeHtml(value) {
    return String(value || '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  class ContactsWidget {
    constructor(mountId, options) {
      this.mountId = mountId;
      this.options = options || {};
    }

    async load() {
      var mount = document.getElementById(this.mountId);
      if (!mount) return;

      try {
        var base = endpointBase(this.options.context, this.options.id);
        var list = await FiberAuth.fetchJson(base + '/contacts');
        if (!Array.isArray(list) || list.length === 0) {
          mount.innerHTML = '<div style="font-size:11px;color:var(--muted)">Контактів поки немає</div>';
          return;
        }
        mount.innerHTML = list.map(function (item) {
          var role = escapeHtml(item.contact_role || 'Контакт');
          var name = escapeHtml(item.name || '—');
          var phone = escapeHtml(item.phone || '');
          return '<div style="padding:8px 10px;border:1px solid var(--border);margin-bottom:6px">' +
            '<div style="font-size:11px;color:var(--muted)">' + role + '</div>' +
            '<div style="font-size:12px;font-weight:500">' + name + '</div>' +
            '<div style="font-size:11px;color:var(--accent)">' + phone + '</div>' +
            '</div>';
        }).join('');
      } catch (_err) {
        mount.innerHTML = '<div style="font-size:11px;color:var(--red)">Не вдалося завантажити контакти</div>';
      }
    }
  }

  class NotesWidget {
    constructor(mountId, options) {
      this.mountId = mountId;
      this.options = options || {};
    }

    noteType(item) {
      return item.comment_type || item.type || 'note';
    }

    async load() {
      var mount = document.getElementById(this.mountId);
      if (!mount) return;

      try {
        var base = endpointBase(this.options.context, this.options.id);
        var list = await FiberAuth.fetchJson(base + '/comments');
        var allowed = this.options.allowedTypes;
        if (Array.isArray(allowed) && allowed.length > 0) {
          list = (list || []).filter((item) => allowed.includes(this.noteType(item)));
        }

        if (!Array.isArray(list) || list.length === 0) {
          mount.innerHTML = '<div style="font-size:11px;color:var(--muted)">Нотаток поки немає</div>';
          return;
        }

        mount.innerHTML = list.map((item) => {
          var body = escapeHtml(item.body || item.comment || '');
          var type = escapeHtml(this.noteType(item));
          return '<div style="padding:8px 10px;border:1px solid var(--border);margin-bottom:6px">' +
            '<div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px">' + type + '</div>' +
            '<div style="font-size:12px">' + body + '</div>' +
            '</div>';
        }).join('');
      } catch (_err) {
        mount.innerHTML = '<div style="font-size:11px;color:var(--red)">Не вдалося завантажити нотатки</div>';
      }
    }
  }

  window.FiberWidgets = {
    ContactsWidget: ContactsWidget,
    NotesWidget: NotesWidget
  };
})();
