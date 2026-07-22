/**
 * Telegram Mini App bootstrap.
 * Sticky shell: body locked, #tg-scroll-root scrolls and receives taps.
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

    function ensureScrollShell() {
        var body = document.body;
        if (!body) return null;

        var existing = document.getElementById("tg-scroll-root");
        if (existing) {
            Array.prototype.slice.call(body.children).forEach(function (el) {
                if (el === existing || el.tagName === "SCRIPT") return;
                existing.appendChild(el);
            });
            return existing;
        }

        var shell = document.createElement("div");
        shell.id = "tg-scroll-root";
        shell.className = "tg-scroll-root";

        var move = [];
        Array.prototype.forEach.call(body.children, function (el) {
            if (!el || el.id === "tg-scroll-root") return;
            if (el.tagName === "SCRIPT") return;
            move.push(el);
        });
        body.insertBefore(shell, body.firstChild);
        move.forEach(function (el) {
            shell.appendChild(el);
        });
        return shell;
    }

    function applyViewport(tg) {
        var root = document.documentElement;
        var body = document.body;
        var shell = document.getElementById("tg-scroll-root");
        try {
            var h = Math.round(tg.viewportStableHeight || tg.viewportHeight || window.innerHeight || 0);
            if (h > 0) {
                root.style.setProperty("--tg-viewport-stable-height", h + "px");
                root.style.height = h + "px";
                root.style.maxHeight = h + "px";
                if (body) {
                    body.style.height = h + "px";
                    body.style.maxHeight = h + "px";
                }
                if (shell) {
                    shell.style.height = h + "px";
                }
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

    function wireExternalLinks(tg) {
        document.addEventListener(
            "click",
            function (e) {
                var a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
                if (!a) return;
                var href = (a.getAttribute("href") || "").trim();
                if (!href || href.charAt(0) === "#" || href.charAt(0) === "/") return;
                if (href.indexOf("mailto:") === 0 || href.indexOf("tel:") === 0) return;
                if (!/^https?:\/\//i.test(href)) return;
                e.preventDefault();
                try {
                    if (/^https?:\/\/t\.me\//i.test(href) && typeof tg.openTelegramLink === "function") {
                        tg.openTelegramLink(href);
                    } else if (typeof tg.openLink === "function") {
                        tg.openLink(href);
                    } else {
                        window.location.href = href;
                    }
                } catch (err) {
                    window.location.href = href;
                }
            },
            true
        );
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

        // Mark early to avoid auth storms if reload races.
        sessionStorage.setItem("tg_webapp_auth_done", "1");

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
                if (res.ok && res.data && res.data.success) {
                    var url = window.location.pathname + window.location.search;
                    window.location.replace(url);
                } else if (hint) {
                    hint.hidden = false;
                    hint.textContent = "Не удалось войти автоматически. Используйте кнопки ниже.";
                }
            })
            .catch(function () {
                if (hint) {
                    hint.hidden = false;
                    hint.textContent = "Не удалось войти автоматически. Используйте кнопки ниже.";
                }
            });
    }

    function boot() {
        var tg = window.Telegram && window.Telegram.WebApp;
        if (!tg) return;

        try {
            document.documentElement.classList.add("tg-webapp");
            document.body.classList.add("tg-webapp");

            ensureScrollShell();

            tg.ready();
            tg.expand();

            if (typeof tg.disableVerticalSwipes === "function") {
                try {
                    tg.disableVerticalSwipes();
                } catch (e) {}
            }

            applyTheme(tg);
            applyViewport(tg);
            wireBackButton(tg);
            wireExternalLinks(tg);

            setTimeout(function () {
                applyViewport(tg);
            }, 50);
            setTimeout(function () {
                applyViewport(tg);
            }, 350);

            if (typeof tg.onEvent === "function") {
                tg.onEvent("viewportChanged", function () {
                    applyViewport(tg);
                });
                tg.onEvent("themeChanged", function () {
                    applyTheme(tg);
                });
            }

            window.__TG_WEBAPP__ = {
                initData: tg.initData || "",
                initDataUnsafe: tg.initDataUnsafe || {},
                version: tg.version || "",
                platform: tg.platform || "",
            };

            tryWebappAuth(tg);
        } catch (e) {
            // Ignore Mini App bootstrap errors outside Telegram.
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
