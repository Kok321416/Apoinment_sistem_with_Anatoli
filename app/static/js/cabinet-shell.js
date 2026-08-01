/**
 * Cabinet shell: mobile sidenav drawer (Flowbite-like).
 */
(function () {
    "use strict";

    function boot() {
        var sidenav = document.getElementById("cabinet-sidenav");
        var backdrop = document.getElementById("cabinet-sidenav-backdrop");
        var btn = document.getElementById("cabinet-menu-btn");
        if (!sidenav || !btn) return;

        function setOpen(open) {
            document.body.classList.toggle("cabinet-sidenav-open", open);
            btn.setAttribute("aria-expanded", open ? "true" : "false");
            if (backdrop) backdrop.hidden = !open;
        }

        btn.addEventListener("click", function () {
            setOpen(!document.body.classList.contains("cabinet-sidenav-open"));
        });
        if (backdrop) {
            backdrop.addEventListener("click", function () {
                setOpen(false);
            });
        }
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape") setOpen(false);
        });
        window.addEventListener("resize", function () {
            if (window.matchMedia("(min-width: 900px)").matches) setOpen(false);
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
