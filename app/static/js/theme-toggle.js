/**
 * Light theme only — clears legacy preference and keeps data-theme=light.
 */
(function (global) {
    "use strict";

    function forceLight() {
        var root = document.documentElement;
        root.setAttribute("data-theme", "light");
        root.style.colorScheme = "light";
        try {
            localStorage.removeItem("ayc_theme");
            localStorage.removeItem("ayc-theme");
        } catch (e) {}
        var meta = document.querySelector('meta[name="theme-color"]');
        if (meta) meta.setAttribute("content", "#ffffff");
        var scheme = document.querySelector('meta[name="color-scheme"]');
        if (scheme) scheme.setAttribute("content", "light");
    }

    forceLight();
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", forceLight);
    }
    global.AycTheme = { forceLight: forceLight, getPreference: function () { return "light"; } };
})(window);
