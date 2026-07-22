(function () {
    "use strict";

    function embedFromUrl(raw) {
        if (!raw) return "";
        var u = String(raw).trim();
        var yt = u.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([\w-]+)/i);
        if (yt) {
            return '<iframe src="https://www.youtube.com/embed/' + yt[1] + '?autoplay=1" allow="autoplay; encrypted-media" allowfullscreen title="Видео"></iframe>';
        }
        var vk = u.match(/vk\.com\/video(-?\d+)_(\d+)/i);
        if (vk) {
            return '<iframe src="https://vk.com/video_ext.php?oid=' + vk[1] + '&id=' + vk[2] + '&autoplay=1" allowfullscreen title="Видео"></iframe>';
        }
        var rutube = u.match(/rutube\.ru\/video\/([a-z0-9]+)/i);
        if (rutube) {
            return '<iframe src="https://rutube.ru/play/embed/' + rutube[1] + '" allowfullscreen title="Видео"></iframe>';
        }
        return "";
    }

    var play = document.getElementById("psVideoPlay");
    var frame = document.querySelector(".ps-video__frame");
    var embedBox = document.getElementById("psVideoEmbed");
    if (play && frame && embedBox) {
        play.addEventListener("click", function () {
            var html = embedFromUrl(frame.getAttribute("data-video-url") || "");
            if (!html) {
                window.open(frame.getAttribute("data-video-url") || "", "_blank", "noopener");
                return;
            }
            embedBox.innerHTML = html;
            embedBox.hidden = false;
            play.hidden = true;
        });
    }

    var sticky = document.getElementById("psSticky");
    var calendars = document.getElementById("psCalendars");
    if (sticky && calendars) {
        function syncSticky() {
            var calTop = calendars.getBoundingClientRect().top;
            var show = window.scrollY > 360 && calTop > 140;
            sticky.hidden = !show;
        }
        window.addEventListener("scroll", syncSticky, { passive: true });
        window.addEventListener("resize", syncSticky);
        syncSticky();
    }

    var grid = document.getElementById("psCalGrid");
    var search = document.getElementById("psCalSearch");
    var sort = document.getElementById("psCalSort");
    var empty = document.getElementById("psCalEmpty");

    function applyFilters() {
        if (!grid) return;
        var q = ((search && search.value) || "").trim().toLowerCase();
        var mode = (sort && sort.value) || "name";
        var cards = Array.prototype.slice.call(grid.querySelectorAll(".ps-cal-card"));
        var visible = 0;
        cards.forEach(function (card) {
            var name = card.getAttribute("data-name") || "";
            var show = !q || name.indexOf(q) !== -1;
            card.classList.toggle("is-hidden", !show);
            if (show) visible += 1;
        });
        if (empty) empty.hidden = visible > 0;
        cards.sort(function (a, b) {
            if (mode === "services") {
                return (
                    parseInt(b.getAttribute("data-services") || "0", 10) -
                    parseInt(a.getAttribute("data-services") || "0", 10)
                );
            }
            return (a.getAttribute("data-name") || "").localeCompare(b.getAttribute("data-name") || "", "ru");
        });
        cards.forEach(function (card) {
            grid.appendChild(card);
        });
    }

    if (search) search.addEventListener("input", applyFilters);
    if (sort) sort.addEventListener("change", applyFilters);
})();
