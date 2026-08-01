(function (global) {
    "use strict";

    function formatRelative(iso) {
        if (!iso) return "—";
        try {
            var d = new Date(iso);
            var diff = Date.now() - d.getTime();
            var mins = Math.floor(diff / 60000);
            if (mins < 1) return "только что";
            if (mins < 60) return mins + " мин. назад";
            var hours = Math.floor(mins / 60);
            if (hours < 24) return hours + " ч. назад";
            var days = Math.floor(hours / 24);
            if (days === 1) return "вчера";
            if (days < 7) return days + " дн. назад";
            return d.toLocaleDateString("ru-RU");
        } catch (e) {
            return iso;
        }
    }

    function formatRelativeFuture(iso) {
        if (!iso) return "Нет записей";
        try {
            var d = new Date(iso + "T12:00:00");
            var today = new Date();
            today.setHours(0, 0, 0, 0);
            var diff = today - d;
            var days = Math.floor(diff / 86400000);
            if (days === 0) return "сегодня";
            if (days === 1) return "вчера";
            if (days < 7) return days + " дн. назад";
            if (days < 30) return Math.floor(days / 7) + " нед. назад";
            return d.toLocaleDateString("ru-RU");
        } catch (e) {
            return iso;
        }
    }

    function loadData() {
        var node = document.getElementById("calendars-hub-data");
        if (!node) return { dashboard: {}, calendars: [] };
        try {
            return JSON.parse(node.textContent || "{}");
        } catch (e) {
            return { dashboard: {}, calendars: [] };
        }
    }

    function openCreateForm() {
        var panel = document.getElementById("calendars-create");
        var toggle = document.getElementById("calendars-create-toggle");
        if (panel) {
            panel.hidden = false;
            var input = panel.querySelector("#calendar_name");
            if (input) input.focus();
        }
        if (toggle) toggle.hidden = true;
    }

    function closeCreateForm() {
        var panel = document.getElementById("calendars-create");
        var toggle = document.getElementById("calendars-create-toggle");
        if (panel) panel.hidden = true;
        if (toggle) toggle.hidden = false;
    }

    function initRelativeDates() {
        document.querySelectorAll("[data-relative]").forEach(function (el) {
            var iso = el.getAttribute("data-relative");
            if (!iso) return;
            if (el.classList.contains("cal-card__meta-value--booking")) {
                el.textContent = formatRelativeFuture(iso);
            } else {
                el.textContent = formatRelative(iso);
            }
        });
    }

    function initHero(dashboard) {
        var updated = document.getElementById("calendars-hero-updated");
        if (updated && dashboard.last_updated) {
            updated.textContent = "Последнее изменение: " + formatRelative(dashboard.last_updated);
        }
    }

    function stubAction(message) {
        if (typeof global.showToast === "function") {
            global.showToast(message, "success");
        } else {
            window.alert(message);
        }
    }

    function init() {
        var page = document.getElementById("calendars-page");
        if (!page) return;

        var data = loadData();
        initHero(data.dashboard || {});
        initRelativeDates();

        document.getElementById("btn-new-calendar") && document.getElementById("btn-new-calendar").addEventListener("click", openCreateForm);
        document.getElementById("btn-hero-new-calendar") && document.getElementById("btn-hero-new-calendar").addEventListener("click", openCreateForm);
        document.getElementById("btn-empty-create") && document.getElementById("btn-empty-create").addEventListener("click", openCreateForm);
        document.getElementById("calendars-create-toggle") && document.getElementById("calendars-create-toggle").addEventListener("click", openCreateForm);
        document.getElementById("btn-close-create") && document.getElementById("btn-close-create").addEventListener("click", closeCreateForm);

        document.getElementById("btn-import-calendars") && document.getElementById("btn-import-calendars").addEventListener("click", function () {
            stubAction("Импорт календарей скоро будет доступен");
        });
        document.getElementById("btn-export-calendars") && document.getElementById("btn-export-calendars").addEventListener("click", function () {
            stubAction("Экспорт календарей скоро будет доступен");
        });
        document.getElementById("btn-public-qr") && document.getElementById("btn-public-qr").addEventListener("click", function () {
            stubAction("QR-код скоро будет доступен");
        });

        document.querySelectorAll("[data-stub-stats]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                stubAction("Статистика календаря скоро будет доступна");
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})(window);
