(function () {
    function init() {
        var sidebar = document.getElementById("profile-sidebar");
        var panels = document.querySelectorAll(".profile-panel[data-panel]");
        var authPanel = document.getElementById("auth-panel");
        var page = document.getElementById("profile-page");
        if (!sidebar) return;

        function isCompact() {
            return window.matchMedia("(max-width: 900px)").matches || document.body.classList.contains("tg-webapp");
        }

        function showTab(tab, opts) {
            if (!tab) return;
            opts = opts || {};

            sidebar.querySelectorAll(".profile-sidebar__btn").forEach(function (btn) {
                var on = btn.dataset.tab === tab;
                btn.classList.toggle("is-active", on);
                btn.setAttribute("aria-selected", on ? "true" : "false");
            });

            var activePanel = null;
            panels.forEach(function (panel) {
                var match = panel.dataset.panel === tab;
                if (match) {
                    panel.hidden = false;
                    panel.classList.remove("is-leaving");
                    panel.classList.add("is-active");
                    activePanel = panel;
                    requestAnimationFrame(function () {
                        panel.classList.add("is-entering");
                    });
                } else if (panel.id !== "auth-panel") {
                    panel.classList.remove("is-entering", "is-active");
                    panel.classList.add("is-leaving");
                    panel.hidden = true;
                }
            });

            if (authPanel) {
                var authOn = tab === "auth";
                authPanel.hidden = !authOn;
                authPanel.classList.toggle("is-active", authOn);
                if (authOn) activePanel = authPanel;
            }

            if (page) {
                page.setAttribute("data-active-tab", tab);
            }

            try {
                if (history.replaceState) {
                    var url = new URL(window.location.href);
                    url.searchParams.set("tab", tab);
                    history.replaceState(null, "", url.pathname + url.search + url.hash);
                }
            } catch (e) {}

            if (opts.scroll !== false && activePanel && isCompact()) {
                window.setTimeout(function () {
                    var target = activePanel;
                    var scrollRoot = document.getElementById("tg-scroll-root");
                    try {
                        target.scrollIntoView({ behavior: "smooth", block: "start" });
                    } catch (err) {
                        target.scrollIntoView(true);
                    }
                    // Focus first field so keyboard opens in Mini App / mobile
                    var field = target.querySelector("input:not([type=hidden]):not([type=file]), textarea, select");
                    if (field && opts.focus !== false) {
                        try {
                            field.focus({ preventScroll: true });
                        } catch (e2) {
                            try {
                                field.focus();
                            } catch (e3) {}
                        }
                    }
                    if (scrollRoot && scrollRoot.scrollTop != null) {
                        // Keep sticky menu visible: nudge a bit up if needed
                        var menu = document.querySelector("[data-profile-menu]");
                        if (menu) {
                            var rect = target.getBoundingClientRect();
                            var menuH = menu.getBoundingClientRect().height || 0;
                            if (rect.top < menuH + 8) {
                                scrollRoot.scrollTop = Math.max(0, scrollRoot.scrollTop - (menuH + 12 - rect.top));
                            }
                        }
                    }
                }, 40);
            }
        }

        sidebar.querySelectorAll(".profile-sidebar__btn").forEach(function (btn) {
            btn.setAttribute("role", "tab");
            btn.addEventListener("click", function (e) {
                e.preventDefault();
                showTab(btn.dataset.tab, { scroll: true, focus: true });
            });
        });

        document.querySelectorAll(".progress-card__item[data-tab]").forEach(function (item) {
            item.addEventListener("click", function () {
                showTab(item.getAttribute("data-tab"), { scroll: true, focus: true });
            });
        });

        window.profileShowTab = showTab;

        var initial = "basic";
        try {
            var q = new URLSearchParams(window.location.search).get("tab");
            if (q && sidebar.querySelector('.profile-sidebar__btn[data-tab="' + q + '"]')) {
                initial = q;
            }
        } catch (e) {}
        showTab(initial, { scroll: false, focus: false });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
