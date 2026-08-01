/**
 * Theme: Cal-like light / dark / system.
 * Storage key: ayc_theme = "light" | "dark" | "system"
 */
(function (global) {
    "use strict";

    var STORAGE_KEY = "ayc_theme";

    function systemTheme() {
        try {
            return global.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
        } catch (e) {
            return "dark";
        }
    }

    function getPreference() {
        try {
            var v = localStorage.getItem(STORAGE_KEY);
            if (v === "light" || v === "dark" || v === "system") return v;
        } catch (e) {}
        return "system";
    }

    function resolveTheme(pref) {
        return pref === "system" ? systemTheme() : pref;
    }

    function applyTheme(resolved) {
        var root = document.documentElement;
        root.setAttribute("data-theme", resolved);
        root.style.colorScheme = resolved;
        var meta = document.querySelector('meta[name="theme-color"]');
        if (meta) {
            meta.setAttribute("content", resolved === "light" ? "#ffffff" : "#0a0a0a");
        }
        var scheme = document.querySelector('meta[name="color-scheme"]');
        if (scheme) {
            scheme.setAttribute("content", "light dark");
        }
        try {
            if (global.Capacitor && global.Capacitor.Plugins && global.Capacitor.Plugins.StatusBar) {
                var StatusBar = global.Capacitor.Plugins.StatusBar;
                var style = resolved === "light" ? "LIGHT" : "DARK";
                StatusBar.setStyle({ style: style }).catch(function () {});
                if (StatusBar.setBackgroundColor) {
                    StatusBar.setBackgroundColor({
                        color: resolved === "light" ? "#ffffff" : "#0a0a0a",
                    }).catch(function () {});
                }
            }
        } catch (e) {}
        document.dispatchEvent(
            new CustomEvent("ayc:themechange", { detail: { theme: resolved, preference: getPreference() } })
        );
    }

    function setPreference(pref) {
        if (pref !== "light" && pref !== "dark" && pref !== "system") return;
        try {
            localStorage.setItem(STORAGE_KEY, pref);
        } catch (e) {}
        applyTheme(resolveTheme(pref));
        syncToggles();
    }

    function cyclePreference() {
        var order = ["system", "light", "dark"];
        var cur = getPreference();
        var next = order[(order.indexOf(cur) + 1) % order.length];
        setPreference(next);
    }

    function labelFor(pref) {
        if (pref === "light") return "Светлая";
        if (pref === "dark") return "Тёмная";
        return "Системная";
    }

    function syncToggles() {
        var pref = getPreference();
        var resolved = resolveTheme(pref);
        document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
            btn.setAttribute("data-theme-pref", pref);
            btn.setAttribute("data-theme-resolved", resolved);
            btn.setAttribute("aria-label", "Тема: " + labelFor(pref) + ". Нажмите, чтобы сменить");
            var text = btn.querySelector("[data-theme-label]");
            if (text) text.textContent = labelFor(pref);
        });
    }

    function boot() {
        applyTheme(resolveTheme(getPreference()));
        syncToggles();
        document.addEventListener("click", function (e) {
            var btn = e.target && e.target.closest ? e.target.closest("[data-theme-toggle]") : null;
            if (!btn) return;
            e.preventDefault();
            cyclePreference();
        });
        try {
            global.matchMedia("(prefers-color-scheme: light)").addEventListener("change", function () {
                if (getPreference() === "system") {
                    applyTheme(systemTheme());
                    syncToggles();
                }
            });
        } catch (e) {}
    }

    global.AycTheme = {
        getPreference: getPreference,
        setPreference: setPreference,
        resolve: function () {
            return resolveTheme(getPreference());
        },
        cycle: cyclePreference,
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})(window);
