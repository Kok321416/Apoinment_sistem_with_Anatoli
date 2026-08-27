(function () {
    var root = document.getElementById('client-detail');
    if (!root) return;

    var tabs = Array.from(root.querySelectorAll('.crm-tabs__btn'));
    var panels = {
        overview: document.getElementById('panel-overview'),
        bookings: document.getElementById('panel-bookings'),
        diagnostics: document.getElementById('panel-diagnostics'),
        notes: document.getElementById('panel-notes'),
        history: document.getElementById('panel-bookings')
    };

    function activate(name) {
        if (name === 'history') name = 'bookings';
        if (!panels[name]) name = 'overview';
        tabs.forEach(function (btn) {
            var on = btn.getAttribute('data-tab') === name;
            btn.classList.toggle('is-active', on);
            btn.setAttribute('aria-selected', on ? 'true' : 'false');
        });
        Object.keys(panels).forEach(function (key) {
            if (key === 'history') return;
            var panel = panels[key];
            if (!panel) return;
            panel.hidden = key !== name;
        });
        try {
            if (history.replaceState) {
                history.replaceState(null, '', '#' + name);
            }
        } catch (e) {}
    }

    tabs.forEach(function (btn) {
        btn.addEventListener('click', function () {
            activate(btn.getAttribute('data-tab') || 'overview');
        });
    });

    root.querySelectorAll('[data-goto-tab]').forEach(function (el) {
        el.addEventListener('click', function () {
            activate(el.getAttribute('data-goto-tab') || 'overview');
        });
    });

    var hash = (location.hash || '').replace(/^#/, '');
    if (panels[hash] || hash === 'history') activate(hash);
})();
