(function () {
    var COOKIE_NAME = "ayc_consent";
    var MAX_AGE_SEC = 60 * 60 * 24 * 365;

    function readConsent() {
        try {
            var raw = document.cookie.split(";").map(function (p) { return p.trim(); })
                .find(function (p) { return p.indexOf(COOKIE_NAME + "=") === 0; });
            if (!raw) return null;
            return JSON.parse(decodeURIComponent(raw.slice(COOKIE_NAME.length + 1)));
        } catch (e) {
            return null;
        }
    }

    function writeConsent(value) {
        var encoded = encodeURIComponent(JSON.stringify(value));
        var secure = location.protocol === "https:" ? "; Secure" : "";
        document.cookie = COOKIE_NAME + "=" + encoded +
            "; Path=/; Max-Age=" + MAX_AGE_SEC + "; SameSite=Lax" + secure;
        try {
            window.dispatchEvent(new CustomEvent("ayc-consent-changed", { detail: value }));
        } catch (e) {}
    }

    function hideBanner() {
        var el = document.getElementById("cookie-consent");
        if (el) el.hidden = true;
    }

    function showBanner() {
        var el = document.getElementById("cookie-consent");
        if (el) el.hidden = false;
    }

    window.aycConsent = {
        get: readConsent,
        set: writeConsent,
        allowsAnalytics: function () {
            var c = readConsent();
            return !!(c && c.analytics);
        },
    };

    document.addEventListener("DOMContentLoaded", function () {
        var existing = readConsent();
        if (existing && typeof existing.necessary !== "undefined") {
            hideBanner();
            return;
        }
        showBanner();
        var acceptAll = document.getElementById("cookie-accept-all");
        var necessaryOnly = document.getElementById("cookie-necessary-only");
        if (acceptAll) {
            acceptAll.addEventListener("click", function () {
                writeConsent({ necessary: true, analytics: true, v: 1, ts: Date.now() });
                hideBanner();
            });
        }
        if (necessaryOnly) {
            necessaryOnly.addEventListener("click", function () {
                writeConsent({ necessary: true, analytics: false, v: 1, ts: Date.now() });
                hideBanner();
            });
        }
    });
})();
