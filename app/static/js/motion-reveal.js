/**
 * Scroll reveal — Intersection Observer.
 * Progressive: content stays visible until we mark near-viewport items,
 * then enable hide-until-visible only for off-screen blocks (no black flash).
 */
(function () {
    function revealAll(nodes) {
        nodes.forEach(function (el) {
            el.classList.add("is-visible");
        });
    }

    function init() {
        var nodes = document.querySelectorAll(".reveal, .reveal-stagger");
        if (!nodes.length) return;

        var reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
        if (reduce.matches || !("IntersectionObserver" in window)) {
            revealAll(nodes);
            return;
        }

        var vh = window.innerHeight || 800;
        nodes.forEach(function (el) {
            var rect = el.getBoundingClientRect();
            if (rect.top < vh * 1.15) {
                el.classList.add("is-visible");
            }
        });

        document.documentElement.classList.add("js-reveal");

        var observer = new IntersectionObserver(
            function (entries) {
                entries.forEach(function (entry) {
                    if (!entry.isIntersecting) return;
                    entry.target.classList.add("is-visible");
                    observer.unobserve(entry.target);
                });
            },
            {
                root: null,
                rootMargin: "120px 0px 120px 0px",
                threshold: 0.01,
            }
        );

        nodes.forEach(function (el) {
            if (!el.classList.contains("is-visible")) {
                observer.observe(el);
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
