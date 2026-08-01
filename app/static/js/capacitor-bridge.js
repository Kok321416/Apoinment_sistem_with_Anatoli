/**
 * Native Capacitor bridge for Android shell (no-op in normal browsers).
 * Same site + same session/OAuth; only status bar / back / splash polish.
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

    async function boot() {
        if (!isNative()) return;

        document.documentElement.classList.add("capacitor-native");
        document.body && document.body.classList.add("capacitor-native");

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
