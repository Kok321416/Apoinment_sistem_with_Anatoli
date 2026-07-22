/**
 * Bootstrap Telegram Mini App (WebApp) when opened inside Telegram.
 * Safe no-op outside Telegram.
 */
(function () {
    "use strict";

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

            if (typeof tg.enableClosingConfirmation === "function") {
                // Only for multi-step booking forms if needed later.
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
