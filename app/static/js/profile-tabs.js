(function () {
    function init() {
        var sidebar = document.getElementById('profile-sidebar');
        var panels = document.querySelectorAll('.profile-panel[data-panel]');
        var authPanel = document.getElementById('auth-panel');

        function showTab(tab) {
            sidebar.querySelectorAll('.profile-sidebar__btn').forEach(function (btn) {
                btn.classList.toggle('is-active', btn.dataset.tab === tab);
            });
            panels.forEach(function (panel) {
                if (panel.dataset.panel === tab) {
                    panel.hidden = false;
                    panel.classList.add('is-active');
                } else if (panel.id !== 'auth-panel') {
                    panel.hidden = true;
                    panel.classList.remove('is-active');
                }
            });
            if (authPanel) {
                authPanel.hidden = tab !== 'auth';
                if (tab === 'auth') authPanel.classList.add('is-active');
            }
        }

        sidebar.querySelectorAll('.profile-sidebar__btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                showTab(btn.dataset.tab);
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
