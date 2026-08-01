/* Static-only service worker for PWA / Capacitor WebView.
   Does not cache HTML or API (avoids stale CSRF / auth pages).
   /static/* uses network-first so design updates appear in the phone app. */
const CACHE = "ayc-static-v4";

self.addEventListener("install", function (event) {
    self.skipWaiting();
});

self.addEventListener("activate", function (event) {
    event.waitUntil(
        caches.keys().then(function (keys) {
            return Promise.all(
                keys.map(function (k) {
                    return caches.delete(k);
                })
            );
        }).then(function () {
            return self.clients.claim();
        })
    );
});

self.addEventListener("fetch", function (event) {
    var req = event.request;
    if (req.method !== "GET") return;
    var url;
    try {
        url = new URL(req.url);
    } catch (e) {
        return;
    }
    if (url.origin !== self.location.origin) return;
    if (url.pathname.indexOf("/static/") !== 0) return;

    event.respondWith(
        caches.open(CACHE).then(function (cache) {
            return fetch(req)
                .then(function (res) {
                    if (res && res.ok) {
                        cache.put(req, res.clone());
                    }
                    return res;
                })
                .catch(function () {
                    return cache.match(req).then(function (hit) {
                        return hit || Response.error();
                    });
                });
        })
    );
});
