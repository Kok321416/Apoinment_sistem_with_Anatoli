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

    function applySafeArea(tg) {
        var root = document.documentElement;
        function px(n) {
            var v = Number(n);
            return (isFinite(v) && v > 0 ? Math.round(v) : 0) + "px";
        }
        try {
            var sa = tg.safeAreaInset || {};
            var csa = tg.contentSafeAreaInset || {};
            root.style.setProperty("--tg-safe-area-inset-top", px(sa.top));
            root.style.setProperty("--tg-safe-area-inset-bottom", px(sa.bottom));
            root.style.setProperty("--tg-safe-area-inset-left", px(sa.left));
            root.style.setProperty("--tg-safe-area-inset-right", px(sa.right));
            root.style.setProperty("--tg-content-safe-area-inset-top", px(csa.top));
            root.style.setProperty("--tg-content-safe-area-inset-bottom", px(csa.bottom));
            root.style.setProperty("--tg-content-safe-area-inset-left", px(csa.left));
            root.style.setProperty("--tg-content-safe-area-inset-right", px(csa.right));
        } catch (e) {}
    }

    function applyViewport(tg) {
        var root = document.documentElement;
        var body = document.body;
        var shell = document.getElementById("tg-scroll-root");
        try {
            applySafeArea(tg);
            var vv = window.visualViewport;
            var h = Math.round(
                tg.viewportStableHeight ||
                    tg.viewportHeight ||
                    (vv && vv.height) ||
                    window.innerHeight ||
                    document.documentElement.clientHeight ||
                    0
            );
            if (!h || h < 200) {
                h = Math.max(window.innerHeight || 0, document.documentElement.clientHeight || 0, 480);
            }
            if (h > 0) {
                root.style.setProperty("--tg-viewport-stable-height", h + "px");
                root.style.setProperty("--app-vh", h + "px");
                root.style.height = h + "px";
                root.style.maxHeight = h + "px";
                root.style.background = "#ffffff";
                if (body) {
                    body.style.height = h + "px";
                    body.style.maxHeight = h + "px";
                    body.style.background = "#ffffff";
                    body.style.color = "#0a0a0a";
                }
                if (shell) {
                    shell.style.height = h + "px";
                    shell.style.background = "#ffffff";
                }
            }
            if (vv) {
                var inner = window.innerHeight || h;
                var keyboard = Math.max(0, Math.round(inner - vv.height - (vv.offsetTop || 0)));
                root.style.setProperty("--tg-keyboard-inset", keyboard + "px");
                root.style.setProperty("--keyboard-inset", keyboard + "px");
                root.classList.toggle("tg-keyboard-open", keyboard > 72);
                root.classList.toggle("keyboard-open", keyboard > 72);
            }
        } catch (e) {}
    }

    function applyTheme(tg) {
        var root = document.documentElement;
        // Product is light-only: never mirror Telegram dark themeParams into UI.
        root.setAttribute("data-tg-theme", "light");
        root.setAttribute("data-theme", "light");
        root.style.colorScheme = "light";
        try {
            localStorage.removeItem("ayc_theme");
        } catch (e) {}
        root.style.setProperty("--tg-bg", "#ffffff");
        root.style.setProperty("--tg-bg-secondary", "#fafafa");
        root.style.setProperty("--tg-button", "#111111");
        root.style.setProperty("--tg-button-text", "#fafafa");
        root.style.setProperty("--tg-text", "#0a0a0a");
        root.style.setProperty("--tg-hint", "#525252");
        try {
            if (typeof tg.setHeaderColor === "function") {
                tg.setHeaderColor("#ffffff");
            }
            if (typeof tg.setBackgroundColor === "function") {
                tg.setBackgroundColor("#ffffff");
            }
        } catch (e2) {}
    }

    function haptic(kind) {
        var tg = window.Telegram && window.Telegram.WebApp;
        if (!tg || !tg.HapticFeedback) return;
        try {
            var h = tg.HapticFeedback;
            if (kind === "success" && h.notificationOccurred) h.notificationOccurred("success");
            else if (kind === "error" && h.notificationOccurred) h.notificationOccurred("error");
            else if (kind === "medium" && h.impactOccurred) h.impactOccurred("medium");
            else if (h.impactOccurred) h.impactOccurred("light");
        } catch (e) {}
    }

    function wireHaptics() {
        document.addEventListener(
            "click",
            function (e) {
                var t = e.target && e.target.closest
                    ? e.target.closest(
                          ".cabinet-bottom-nav__item, .btn--primary, .btn--success, .bookings-segment__btn, .bookings-quick-pill, .view-toggle__btn, [data-tg-haptic]"
                      )
                    : null;
                if (t) haptic("light");
            },
            true
        );
    }

    function wireMainButton(tg) {
        if (!tg.MainButton) return;
        var el = document.querySelector("[data-tg-main-button]");
        if (!el) {
            try {
                tg.MainButton.hide();
            } catch (e) {}
            return;
        }
        var text = (el.getAttribute("data-tg-main-button") || el.textContent || "Продолжить").trim();
        try {
            tg.MainButton.setText(text.slice(0, 64));
            tg.MainButton.color = "#111111";
            tg.MainButton.textColor = "#fafafa";
            tg.MainButton.show();
            tg.MainButton.onClick(function () {
                haptic("medium");
                if (typeof el.click === "function") el.click();
            });
        } catch (e) {}
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
            haptic("light");
            if (window.history.length > 1) {
                window.history.back();
            } else {
                window.location.href = "/tg/";
            }
        });
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
                try {
                    var abs = new URL(href, window.location.href);
                    if (abs.origin === window.location.origin) return;
                } catch (err0) {}
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

    function consumeStartParamAuth(tg) {
        var authed = document.getElementById("tg-hub-authed");
        if (authed && !authed.hidden) return false;

        var start = "";
        try {
            start = String((tg.initDataUnsafe && tg.initDataUnsafe.start_param) || "").trim();
        } catch (e) {}
        if (!start) {
            try {
                start = String(new URLSearchParams(window.location.search).get("tgWebAppStartParam") || "").trim();
            } catch (e2) {}
        }
        if (!start) return false;

        var kind = "";
        var token = "";
        if (start.indexOf("cmp_") === 0) {
            kind = "complete";
            token = start.slice(4);
        } else if (start.indexOf("hnd_") === 0) {
            kind = "handoff";
            token = start.slice(4);
        } else {
            return false;
        }
        if (!token) return false;

        var doneKey = "tg_startapp_auth_done";
        try {
            if (sessionStorage.getItem(doneKey) === start) return false;
            sessionStorage.setItem(doneKey, start);
        } catch (e3) {}

        var url =
            kind === "complete"
                ? "/accounts/telegram/complete/" + encodeURIComponent(token) + "/?stay=1"
                : "/accounts/native-handoff/" + encodeURIComponent(token) + "/";
        window.location.replace(url);
        return true;
    }

    function showAuthedHub(state) {
        var guest = document.getElementById("tg-hub-guest");
        var authed = document.getElementById("tg-hub-authed");
        if (!guest || !authed) return;
        guest.hidden = true;
        authed.hidden = false;
        authed.setAttribute("data-tg-authed", "1");
        document.body.classList.remove("auth-page");
        document.body.classList.add("tg-hub-page");

        var mode = (state && state.mode) || "client";
        var hasC = !!(state && state.has_consultant);
        var clientActions = document.getElementById("tg-hub-actions-client");
        var specActions = document.getElementById("tg-hub-actions-specialist");
        var modeSwitch = document.getElementById("tg-hub-mode-switch");
        var become = document.getElementById("tg-hub-become-specialist");

        if (mode === "specialist" && hasC) {
            if (clientActions) clientActions.hidden = true;
            if (specActions) specActions.hidden = false;
        } else {
            if (clientActions) clientActions.hidden = false;
            if (specActions) specActions.hidden = true;
        }
        if (modeSwitch) {
            modeSwitch.hidden = !hasC;
            modeSwitch.querySelectorAll("a[data-tg-mode]").forEach(function (a) {
                a.classList.toggle("is-active", a.getAttribute("data-tg-mode") === mode);
            });
        }
        if (become) become.hidden = hasC;
    }

    function hydrateTelegramHub(callback) {
        var url = "/api/telegram/hub-state" + (window.location.search || "");
        fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
            .then(function (r) {
                return r.json();
            })
            .then(function (state) {
                if (state && state.authenticated) {
                    showAuthedHub(state);
                    if (callback) callback(true);
                } else if (callback) {
                    callback(false);
                }
            })
            .catch(function () {
                if (callback) callback(false);
            });
    }

    function tryWebappAuth(tg) {
        var authed = document.getElementById("tg-hub-authed");
        var guest = document.getElementById("tg-hub-guest");
        if (!authed && !guest) return;
        if (authed && !authed.hidden) return;
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

        var ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
        var timer = ctrl ? window.setTimeout(function () { ctrl.abort(); }, 25000) : null;
        fetch("/api/telegram/webapp-auth", {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            credentials: "same-origin",
            body: JSON.stringify(body),
            signal: ctrl ? ctrl.signal : undefined,
        })
            .then(function (r) {
                return r.json().then(function (data) {
                    return { ok: r.ok, data: data };
                });
            })
            .then(function (res) {
                if (timer) window.clearTimeout(timer);
                if (res.ok && res.data && res.data.success) {
                    if (res.data.requires_2fa && res.data.redirect) {
                        sessionStorage.removeItem("tg_webapp_auth_done");
                        window.location.replace(res.data.redirect);
                        return;
                    }
                    hydrateTelegramHub(function () {});
                } else if (hint) {
                    hint.hidden = false;
                    hint.textContent = "Не удалось войти автоматически. Используйте кнопки ниже.";
                }
            })
            .catch(function (err) {
                if (timer) window.clearTimeout(timer);
                sessionStorage.removeItem("tg_webapp_auth_done");
                if (window.__AYC_TG_REPORT__) {
                    window.__AYC_TG_REPORT__("auth_fail", String(err && err.name ? err.name : err || "fetch"));
                }
                if (hint) {
                    hint.hidden = false;
                    hint.textContent = "Не удалось войти автоматически. Используйте кнопки ниже.";
                }
            });
    }

    function bootShellOnly() {
        try {
            document.documentElement.classList.add("tg-webapp");
            document.body.classList.add("tg-webapp");
            ensureScrollShell();
            window.__TG_WEBAPP__ = window.__TG_WEBAPP__ || {
                initData: "",
                initDataUnsafe: {},
                version: "",
                platform: "",
                haptic: haptic,
            };
        } catch (e) {}
    }

    function boot() {
        var tg = window.Telegram && window.Telegram.WebApp;
        if (!tg) {
            bootShellOnly();
            return;
        }

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
            wireHaptics();
            wireMainButton(tg);

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
                tg.onEvent("safeAreaChanged", function () {
                    applySafeArea(tg);
                });
                tg.onEvent("contentSafeAreaChanged", function () {
                    applySafeArea(tg);
                });
            }

            if (window.visualViewport) {
                window.visualViewport.addEventListener(
                    "resize",
                    function () {
                        applyViewport(tg);
                    },
                    { passive: true }
                );
                window.visualViewport.addEventListener(
                    "scroll",
                    function () {
                        applyViewport(tg);
                    },
                    { passive: true }
                );
            }

            window.__TG_WEBAPP__ = {
                initData: tg.initData || "",
                initDataUnsafe: tg.initDataUnsafe || {},
                version: tg.version || "",
                platform: tg.platform || "",
                haptic: haptic,
            };

            if (consumeStartParamAuth(tg)) {
                return;
            }
            hydrateTelegramHub(function (authed) {
                if (!authed) tryWebappAuth(tg);
            });
            // Site/native links point to t.me — inside Mini App stay on the hub.
            try {
                document.querySelectorAll("a[data-tg-internal]").forEach(function (a) {
                    var internal = (a.getAttribute("data-tg-internal") || "").trim();
                    if (!internal) return;
                    a.setAttribute("href", internal);
                    a.removeAttribute("target");
                });
            } catch (e) {}
            // Mark auth links so OAuth / Telegram login returns into Mini App context.
            document.addEventListener(
                "click",
                function (e) {
                    var a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
                    if (!a) return;
                    var href = (a.getAttribute("href") || "").trim();
                    if (
                        href.indexOf("/accounts/telegram/login") === -1 &&
                        href.indexOf("/accounts/yandex/login") === -1 &&
                        href.indexOf("/accounts/vk/login") === -1 &&
                        href.indexOf("/register/") === -1 &&
                        href.indexOf("/login/") === -1
                    ) {
                        return;
                    }
                    if (href.indexOf("client=") !== -1) return;
                    var sep = href.indexOf("?") >= 0 ? "&" : "?";
                    a.setAttribute("href", href + sep + "client=tg");
                },
                true
            );
        } catch (e) {
            // Ignore Mini App bootstrap errors outside Telegram.
        }
    }

    function scheduleBoot() {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", boot);
        } else {
            boot();
        }
    }

    scheduleBoot();
    if (!(window.Telegram && window.Telegram.WebApp)) {
        var tries = 0;
        var waitSdk = window.setInterval(function () {
            tries += 1;
            if (window.Telegram && window.Telegram.WebApp) {
                window.clearInterval(waitSdk);
                boot();
            } else if (tries >= 20) {
                window.clearInterval(waitSdk);
            }
        }, 100);
    }
})();
