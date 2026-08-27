/**
 * Sync --app-vh / --keyboard-inset for site + Mini App.
 * Avoids clipped layouts from fixed 100vh when the mobile keyboard opens.
 */
(function () {
    "use strict";

    function roundPx(n) {
        var v = Math.round(Number(n) || 0);
        return (v > 0 ? v : 0) + "px";
    }

    function sync() {
        var root = document.documentElement;
        if (!root) return;

        var inner = window.innerHeight || root.clientHeight || 0;
        var vv = window.visualViewport;
        var visible = vv && vv.height ? vv.height : inner;
        if (!visible || visible < 120) {
            visible = Math.max(inner, root.clientHeight || 0, 320);
        }

        root.style.setProperty("--app-vh", roundPx(visible));

        var offsetTop = vv && typeof vv.offsetTop === "number" ? vv.offsetTop : 0;
        var keyboard = Math.max(0, inner - visible - offsetTop);
        root.style.setProperty("--keyboard-inset", roundPx(keyboard));
        root.classList.toggle("keyboard-open", keyboard > 72);

        if (root.classList.contains("tg-webapp")) {
            root.style.setProperty("--tg-keyboard-inset", roundPx(keyboard));
        }
    }

    var scheduled = false;
    function schedule() {
        if (scheduled) return;
        scheduled = true;
        requestAnimationFrame(function () {
            scheduled = false;
            sync();
        });
    }

    sync();
    window.addEventListener("resize", schedule, { passive: true });
    window.addEventListener("orientationchange", schedule, { passive: true });
    if (window.visualViewport) {
        window.visualViewport.addEventListener("resize", schedule, { passive: true });
        window.visualViewport.addEventListener("scroll", schedule, { passive: true });
    }
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", sync);
    }
})();
