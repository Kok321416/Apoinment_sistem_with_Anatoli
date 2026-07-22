/**
 * Bootstrap Telegram Mini App (WebApp) when opened inside Telegram.
 * Safe no-op outside Telegram.
 * Phase 8: silent session via initData on /tg/ hub.
 */
(function () {
    "use strict";

    function qsMode() {
        try {
            var m = new URLSearchParams(window.location.search).get("mode");
            if (m === "client" || m === "specialist") return m;
        } catch (e) {}
        return "";
    }

    function applyViewport(tg) {
        var root = document.documentElement;
        var body = document.body;
        try {
            var h = tg.viewportStableHeight || tg.viewportHeight;
            if (h) {
                root.style.setProperty("--tg-viewport-stable-height", h + "px");
            }
            // Keep document height fluid so long pages can scroll in Telegram WebView.
            root.style.height = "auto";
            root.style.maxHeight = "none";
            root.style.overflowY = "auto";
            if (body) {
                body.style.height = "auto";
                body.style.maxHeight = "none";
                body.style.overflowY = "auto";
                body.style.minHeight = (h ? h + "px" : "") || "";
            }
        } catch (e) {}
    }

    function applyTheme(tg) {
        var root = document.documentElement;
        var tp = tg.themeParams || {};
        if (tg.colorScheme === "dark") {
            root.setAttribute("data-tg-theme", "dark");
        } else {
            root.setAttribute("data-tg-theme", "light");
        }
        if (tp.bg_color) root.style.setProperty("--tg-bg", tp.bg_color);
        if (tp.secondary_bg_color) root.style.setProperty("--tg-bg-secondary", tp.secondary_bg_color);
        if (tp.button_color) root.style.setProperty("--tg-button", tp.button_color);
        if (tp.button_text_color) root.style.setProperty("--tg-button-text", tp.button_text_color);
        if (tp.text_color) root.style.setProperty("--tg-text", tp.text_color);
        if (tp.hint_color) root.style.setProperty("--tg-hint", tp.hint_color);
        try {
            if (typeof tg.setHeaderColor === "function") {
                tg.setHeaderColor(tp.bg_color || "#0b0d12");
            }
            if (typeof tg.setBackgroundColor === "function") {
                tg.setBackgroundColor(tp.bg_color || "#0b0d12");
            }
        } catch (e) {}
    }

    function tryWebappAuth(tg) {
        var hub = document.querySelector("[data-tg-hub]");
        if (!hub) return;
        if (hub.getAttribute("data-tg-authed") === "1") return;
        var initData = tg.initData || "";
        if (!initData) return;
        if (sessionStorage.getItem("tg_webapp_auth_done") === "1") return;

        var hint = document.getElementById("tg-auth-hint");
        if (hint) hint.hidden = false;

        var body = { init_data: initData };
        var mode = qsMode();
        if (mode) body.mode = mode;

        fetch("/api/telegram/webapp-auth", {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            credentials: "same-origin",
            body: JSON.stringify(body),
        })
            .then(function (r) {
                return r.json().then(function (data) {
                    return { ok: r.ok, data: data };
                });
            })
            .then(function (res) {
                sessionStorage.setItem("tg_webapp_auth_done", "1");
                if (res.ok && res.data && res.data.success) {
                    var url = window.location.pathname + window.location.search;
                    window.location.replace(url);
                } else if (hint) {
                    hint.textContent = "Не удалось войти автоматически. Используйте «Войти».";
                }
            })
            .catch(function () {
                sessionStorage.setItem("tg_webapp_auth_done", "1");
                if (hint) {
                    hint.textContent = "Не удалось войти автоматически. Используйте «Войти».";
                }
            });
    }

    function wireBackButton(tg) {
        if (!tg.BackButton) return;
        var path = window.location.pathname || "/";
        var isHub = path === "/tg/" || path === "/tg";
        if (isHub) {
            tg.BackButton.hide();
            return;
        }
        tg.BackButton.show();
        tg.BackButton.onClick(function () {
            if (window.history.length > 1) {
                window.history.back();
            } else {
                window.location.href = "/tg/";
            }
        });
    }

    function boot() {
        var tg = window.Telegram && window.Telegram.WebApp;
        if (!tg) return;

        try {
            tg.ready();
            tg.expand();
            // Prefer content scroll over Telegram closing-swipe when API allows.
            if (typeof tg.disableVerticalSwipes === "function") {
                try {
                    tg.disableVerticalSwipes();
                } catch (e) {}
            }
            if (typeof tg.setHeaderColor === "function") {
                try {
                    tg.setHeaderColor("secondary_bg_color");
                } catch (e) {}
            }

            document.documentElement.classList.add("tg-webapp");
            document.body.classList.add("tg-webapp");
            document.documentElement.style.overflowY = "auto";
            document.body.style.overflowY = "auto";
            document.documentElement.style.height = "auto";
            document.body.style.height = "auto";

            applyTheme(tg);
            applyViewport(tg);
            // Re-apply after expand animation settles.
            setTimeout(function () {
                applyViewport(tg);
            }, 300);
            if (typeof tg.onEvent === "function") {
                tg.onEvent("viewportChanged", function () {
                    applyViewport(tg);
                });
                tg.onEvent("themeChanged", function () {
                    applyTheme(tg);
                });
            }

            wireBackButton(tg);

            window.__TG_WEBAPP__ = {
                initData: tg.initData || "",
                initDataUnsafe: tg.initDataUnsafe || {},
                version: tg.version || "",
                platform: tg.platform || "",
            };

            tryWebappAuth(tg);
        } catch (e) {
            // Ignore Mini App bootstrap errors in regular browsers.
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
