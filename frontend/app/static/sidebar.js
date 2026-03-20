document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('sidebar-inject');
    if (!sidebar) return;

    const currentPath = window.location.pathname;
    const isMobile = window.matchMedia('(max-width: 820px)').matches;

    const links = [
        { path: '/designer', label: 'Проєктування', icon: '◈' },
        { path: '/dispatcher', label: 'Диспетчер', icon: '▣' },
        { path: '/connections-dispatch', label: 'Підключення', icon: '◉' },
        { path: '/warehouse', label: 'Склад', icon: '◎' },
        { path: '/field', label: 'Виїзди', icon: '⬤' }
    ];

    let html = '';
    if (!isMobile) {
        html = `
            <div style="padding: 24px; font-weight: 800; color: var(--accent); font-size: 18px; letter-spacing: 2px;">
                FiberOps
            </div>
            <nav style="flex: 1; padding: 0 12px; display: flex; flex-direction: column; gap: 4px;">
        `;
    } else {
        html = `
            <nav style="padding: 8px 10px; display: flex; align-items: center; gap: 6px; overflow-x: auto; white-space: nowrap;">
        `;
    }

    links.forEach(link => {
        const isActive = currentPath.startsWith(link.path);
        html += `
            <a href="${link.path}" class="${isActive ? 'active' : ''}" style="
                display: flex; align-items: center; gap: 12px; padding: 12px 16px; 
                border-radius: var(--radius-md); font-size: 13px; font-weight: 500;
                transition: all 0.2s;
                flex: ${isMobile ? '0 0 auto' : '0 1 auto'};
                ${isActive ? 'background: var(--accent-glow); color: var(--accent); border: 1px solid rgba(0,191,255,0.2);' : 'color: var(--text-secondary);'}
            ">
                <span style="font-size: 16px;">${link.icon}</span>
                <span>${isMobile ? '' : link.label}</span>
            </a>
        `;
    });

    if (!isMobile) {
        html += `
            </nav>
            <div style="padding: 24px; border-top: 1px solid var(--border); font-size: 11px; color: var(--text-muted);">
                v2.4.0-stable
            </div>
        `;
    } else {
        html += `
            </nav>
        `;
    }

    sidebar.innerHTML = html;
});
