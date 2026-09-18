/**
 * Statistics hub: status filter UX, row selection, delete confirm.
 */
(function () {
    "use strict";

    function syncStatusPills() {
        var all = document.getElementById("stats-status-all");
        var opts = Array.prototype.slice.call(document.querySelectorAll(".stats-status-opt"));
        if (!all || !opts.length) return;

        function refreshActive() {
            var any = opts.some(function (el) { return el.checked; });
            if (any) {
                all.checked = false;
            }
            document.querySelectorAll(".stats-status-pill").forEach(function (label) {
                var input = label.querySelector("input");
                if (!input) return;
                if (input.id === "stats-status-all") {
                    label.classList.toggle("is-active", !!all.checked && !any);
                } else {
                    label.classList.toggle("is-active", !!input.checked);
                }
            });
        }

        all.addEventListener("change", function () {
            if (all.checked) {
                opts.forEach(function (el) { el.checked = false; });
            }
            refreshActive();
        });
        opts.forEach(function (el) {
            el.addEventListener("change", function () {
                if (el.checked) all.checked = false;
                var any = opts.some(function (o) { return o.checked; });
                if (!any) all.checked = true;
                refreshActive();
            });
        });

        var form = document.getElementById("stats-range-form");
        if (form) {
            form.addEventListener("submit", function () {
                // Do not send status_all; empty status list = all
                if (all.checked) {
                    opts.forEach(function (el) { el.checked = false; });
                }
                all.disabled = true;
            });
        }
        refreshActive();
    }

    function syncSelection() {
        var checks = Array.prototype.slice.call(document.querySelectorAll(".stats-row-check"));
        var all = document.getElementById("stats-select-all");
        var btn = document.getElementById("stats-delete-btn");
        var form = document.getElementById("stats-delete-form");
        if (!checks.length || !btn || !form) return;

        function update() {
            var n = checks.filter(function (c) { return c.checked; }).length;
            btn.disabled = n === 0;
            btn.textContent = n ? ("Удалить выбранные (" + n + ")") : "Удалить выбранные";
            if (all) {
                all.checked = n > 0 && n === checks.length;
                all.indeterminate = n > 0 && n < checks.length;
            }
        }

        if (all) {
            all.addEventListener("change", function () {
                checks.forEach(function (c) { c.checked = all.checked; });
                update();
            });
        }
        checks.forEach(function (c) {
            c.addEventListener("change", update);
        });
        form.addEventListener("submit", function (e) {
            var n = checks.filter(function (c) { return c.checked; }).length;
            if (!n) {
                e.preventDefault();
                return;
            }
            var ok = window.confirm(
                "Удалить выбранные записи (" + n + ")?\n\n" +
                "Они исчезнут из статистики и Excel. Это действие нельзя отменить."
            );
            if (!ok) e.preventDefault();
        });
        update();
    }

    function boot() {
        syncStatusPills();
        syncSelection();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
