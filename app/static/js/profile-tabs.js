(function () {
    function init() {
        var sidebar = document.getElementById('profile-sidebar');
        var panels = document.querySelectorAll('.profile-panel[data-panel]');
        var authPanel = document.getElementById('auth-panel');
        if (!sidebar) return;

        function showTab(tab) {
            sidebar.querySelectorAll('.profile-sidebar__btn').forEach(function (btn) {
                btn.classList.toggle('is-active', btn.dataset.tab === tab);
            });
            panels.forEach(function (panel) {
                if (panel.dataset.panel === tab) {
                    panel.hidden = false;
                    panel.classList.remove('is-leaving');
                    panel.classList.add('is-active');
                    requestAnimationFrame(function () {
                        panel.classList.add('is-entering');
                    });
                } else if (panel.id !== 'auth-panel') {
                    panel.classList.remove('is-entering', 'is-active');
                    panel.classList.add('is-leaving');
                    panel.hidden = true;
                }
            });
            if (authPanel) {
                authPanel.hidden = tab !== 'auth';
                authPanel.classList.toggle('is-active', tab === 'auth');
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
