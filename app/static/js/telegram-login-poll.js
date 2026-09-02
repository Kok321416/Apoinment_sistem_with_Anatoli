(function () {
    "use strict";

    var root = document.getElementById("telegramLoginPoll");
    if (!root) {
        return;
    }

    var token = root.dataset.token;
    if (!token) {
        return;
    }

    var statusEl = document.getElementById("loginStatus");
    var btn = document.getElementById("btnOpenBot");
    var waitingText =
        root.dataset.waitingText ||
        "Ждем подтверждения авторизации через Telegram...";
    var doneText = root.dataset.doneText || "Готово! Продолжаем запись…";
    var expiredText =
        root.dataset.expiredText ||
        "Ссылка истекла. Обновите страницу и попробуйте снова.";
    var pollMs = parseInt(root.dataset.pollMs || "2000", 10);
    var stopped = false;
    var openedBot = false;

    function isMobileBrowser() {
        return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent || "");
    }

    function inMiniApp() {
        try {
            var w = window.Telegram && window.Telegram.WebApp;
            return !!(w && (w.initData || (w.initDataUnsafe && w.initDataUnsafe.user)));
        } catch (e) {
            return false;
        }
    }

    function inAppCompleteUrl(redirect) {
        var raw = redirect || "";
        var tokenMatch =
            raw.match(/complete\/([^\/\?]+)/) || raw.match(/[?&]token=([^&]+)/);
        if (tokenMatch) {
            return (
                "/accounts/telegram/complete/" +
                decodeURIComponent(tokenMatch[1]) +
                "/?stay=1"
            );
        }
        return "/tg/";
    }

    function showWaiting() {
        if (!statusEl) {
            return;
        }
        statusEl.textContent = waitingText;
        statusEl.hidden = false;
        statusEl.classList.add("tg-status--waiting");
    }

    function openBotLink() {
        if (!btn || openedBot) {
            return;
        }
        openedBot = true;
        showWaiting();
        var href = btn.getAttribute("href") || "";
        var tgHref = btn.dataset.tg || "";
        var webapp = window.Telegram && window.Telegram.WebApp;
        if (
            webapp &&
            href.indexOf("https://t.me/") === 0 &&
            typeof webapp.openTelegramLink === "function"
        ) {
            try {
                webapp.openTelegramLink(href);
                return;
            } catch (err) {
                /* fall through */
            }
        }
        if (isMobileBrowser() && tgHref) {
            window.location.href = tgHref;
            return;
        }
        if (href) {
            window.open(href, "_blank", "noopener");
        }
    }

    function poll() {
        if (stopped) {
            return;
        }
        fetch(
            "/accounts/telegram/login/status/" + encodeURIComponent(token) + "/",
            { credentials: "same-origin", headers: { Accept: "application/json" } }
        )
            .then(function (r) {
                return r.json();
            })
            .then(function (data) {
                if (data.completed && data.redirect) {
                    stopped = true;
                    if (statusEl) {
                        statusEl.textContent = doneText;
                    }
                    var next = data.redirect;
                    if (inMiniApp()) {
                        window.location.replace(inAppCompleteUrl(next));
                        return;
                    }
                    window.location.replace(next);
                    return;
                }
                if (data.error === "expired") {
                    stopped = true;
                    if (statusEl) {
                        statusEl.textContent = expiredText;
                        statusEl.classList.remove("tg-status--waiting");
                    }
                    return;
                }
                setTimeout(poll, pollMs);
            })
            .catch(function () {
                setTimeout(poll, Math.max(pollMs, 3000));
            });
    }

    if (btn) {
        btn.addEventListener("click", function (e) {
            var href = btn.getAttribute("href") || "";
            var webapp = window.Telegram && window.Telegram.WebApp;
            if (
                webapp &&
                href.indexOf("https://t.me/") === 0 &&
                typeof webapp.openTelegramLink === "function"
            ) {
                e.preventDefault();
                openBotLink();
                return;
            }
            if (isMobileBrowser() && btn.dataset.tg) {
                e.preventDefault();
                openBotLink();
                return;
            }
            showWaiting();
            openedBot = true;
        });
    }

    document.addEventListener("visibilitychange", function () {
        if (!document.hidden) {
            poll();
        }
    });
    window.addEventListener("pageshow", function () {
        poll();
    });
    window.addEventListener("focus", function () {
        poll();
    });

    if (root.dataset.autoOpen === "1" && isMobileBrowser()) {
        setTimeout(openBotLink, 400);
    } else {
        showWaiting();
    }

    poll();
})();
