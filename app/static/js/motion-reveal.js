/**
 * Scroll reveal — Intersection Observer
 * Adds .is-visible to .reveal / .reveal-stagger when in viewport.
 * Respects prefers-reduced-motion.
 */
(function () {
    function revealAll(nodes) {
        nodes.forEach(function (el) {
            el.classList.add('is-visible');
        });
    }

    function init() {
        var nodes = document.querySelectorAll('.reveal, .reveal-stagger');
        if (!nodes.length) return;

        var reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
        if (reduce.matches || !('IntersectionObserver' in window)) {
            revealAll(nodes);
            return;
        }

        var observer = new IntersectionObserver(
            function (entries) {
                entries.forEach(function (entry) {
                    if (!entry.isIntersecting) return;
                    entry.target.classList.add('is-visible');
                    observer.unobserve(entry.target);
                });
            },
            {
                root: null,
                rootMargin: '0px 0px -8% 0px',
                threshold: 0.12,
            }
        );

        nodes.forEach(function (el) {
            observer.observe(el);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
