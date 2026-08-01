/**
 * Native Capacitor bridge: status bar, back button, auth client=native, deep links.
 */
(function () {
    "use strict";

    function isNative() {
        try {
            return !!(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform());
        } catch (e) {
            return false;
        }
    }

    function withClientParam(href, client) {
        if (!href || href.charAt(0) === "#" || href.indexOf("mailto:") === 0 || href.indexOf("tel:") === 0) {
            return href;
        }
        if (href.indexOf("client=") !== -1) return href;
        try {
            if (/^https?:\/\//i.test(href)) {
                var u = new URL(href, window.location.origin);
                if (u.origin !== window.location.origin) return href;
                u.searchParams.set("client", client);
                return u.pathname + u.search + u.hash;
            }
        } catch (e) {}
        var sep = href.indexOf("?") >= 0 ? "&" : "?";
        return href + sep + "client=" + encodeURIComponent(client);
    }

    function patchAuthLinks(client) {
        document.addEventListener(
            "click",
            function (e) {
                var a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
                if (!a) return;
                var href = (a.getAttribute("href") || "").trim();
                if (!href) return;
                if (
                    href.indexOf("/accounts/telegram/login") === -1 &&
                    href.indexOf("/accounts/yandex/login") === -1 &&
                    href.indexOf("/accounts/vk/login") === -1
                ) {
                    return;
                }
                var next = withClientParam(href, client);
                if (next !== href) {
                    a.setAttribute("href", next);
                }
            },
            true
        );
    }

    function mapDeepLinkToPath(url) {
        // allyourclients://auth/complete/TOKEN
        // allyourclients://auth/handoff/TOKEN
        try {
            var u = new URL(url);
            if (u.protocol !== "allyourclients:") return "";
            var parts = (u.pathname || "").replace(/^\/+/, "").split("/");
            // Some Android builds put path in host: allyourclients://auth/complete/TOKEN
            if ((!parts[0] || parts[0] === "") && u.host) {
                parts = [u.host].concat((u.pathname || "").replace(/^\/+/, "").split("/").filter(Boolean));
            }
            if (parts[0] === "auth" && parts[1] === "complete" && parts[2]) {
                return "/accounts/telegram/complete/" + encodeURIComponent(parts[2]) + "/";
            }
            if (parts[0] === "auth" && parts[1] === "handoff" && parts[2]) {
                return "/accounts/native-handoff/" + encodeURIComponent(parts[2]) + "/";
            }
        } catch (e) {}
        return "";
    }

    function wireDeepLinks() {
        try {
            var App = window.Capacitor.Plugins && window.Capacitor.Plugins.App;
            if (!App || !App.addListener) return;
            App.addListener("appUrlOpen", function (event) {
                var path = mapDeepLinkToPath((event && event.url) || "");
                if (path) {
                    window.location.href = path;
                }
            });
            if (App.getLaunchUrl) {
                App.getLaunchUrl().then(function (res) {
                    var path = mapDeepLinkToPath((res && res.url) || "");
                    if (path) window.location.href = path;
                }).catch(function () {});
            }
        } catch (e) {}
    }

    async function boot() {
        if (!isNative()) return;

        document.documentElement.classList.add("capacitor-native");
        document.body && document.body.classList.add("capacitor-native");
        try {
            sessionStorage.setItem("ayc_client", "native");
        } catch (e) {}

        patchAuthLinks("native");
        wireDeepLinks();

        try {
            var StatusBar = window.Capacitor.Plugins && window.Capacitor.Plugins.StatusBar;
            if (StatusBar) {
                await StatusBar.setStyle({ style: "DARK" });
                if (StatusBar.setBackgroundColor) {
                    await StatusBar.setBackgroundColor({ color: "#0B0D12" });
                }
            }
        } catch (e) {}

        try {
            var SplashScreen = window.Capacitor.Plugins && window.Capacitor.Plugins.SplashScreen;
            if (SplashScreen && SplashScreen.hide) {
                await SplashScreen.hide();
            }
        } catch (e) {}

        try {
            var App = window.Capacitor.Plugins && window.Capacitor.Plugins.App;
            if (App && App.addListener) {
                App.addListener("backButton", function (ev) {
                    if (window.history.length > 1) {
                        window.history.back();
                    } else if (ev && ev.canGoBack === false && App.exitApp) {
                        App.exitApp();
                    }
                });
            }
        } catch (e) {}
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
