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

    function boot() {
        var tg = window.Telegram && window.Telegram.WebApp;
        if (!tg) return;

        try {
            tg.ready();
            tg.expand();
            document.documentElement.classList.add("tg-webapp");
            document.body.classList.add("tg-webapp");

            if (tg.colorScheme === "dark") {
                document.documentElement.setAttribute("data-tg-theme", "dark");
            }

            if (tg.themeParams) {
                var root = document.documentElement;
                if (tg.themeParams.bg_color) {
                    root.style.setProperty("--tg-bg", tg.themeParams.bg_color);
                }
                if (tg.themeParams.button_color) {
                    root.style.setProperty("--tg-button", tg.themeParams.button_color);
                }
                if (tg.themeParams.text_color) {
                    root.style.setProperty("--tg-text", tg.themeParams.text_color);
                }
            }

            if (tg.BackButton) {
                tg.BackButton.hide();
            }

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
