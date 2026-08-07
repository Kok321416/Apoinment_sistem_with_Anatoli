(function () {
    var root = document.getElementById('client-detail');
    if (!root) return;

    var tabs = Array.from(root.querySelectorAll('.crm-tabs__btn'));
    var panels = {
        overview: document.getElementById('panel-overview'),
        history: document.getElementById('panel-history'),
        notes: document.getElementById('panel-notes')
    };

    function activate(name) {
        tabs.forEach(function (btn) {
            var on = btn.getAttribute('data-tab') === name;
            btn.classList.toggle('is-active', on);
            btn.setAttribute('aria-selected', on ? 'true' : 'false');
        });
        Object.keys(panels).forEach(function (key) {
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

    var hash = (location.hash || '').replace(/^#/, '');
    if (panels[hash]) activate(hash);
})();
