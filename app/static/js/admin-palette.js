(function () {
    var overlay = document.getElementById("paPalette");
    var input = document.getElementById("paPaletteInput");
    var list = document.getElementById("paPaletteResults");
    var timer = null;
    if (!overlay || !input || !list) return;

    function openPalette() {
        overlay.hidden = false;
        overlay.classList.add("is-open");
        input.value = "";
        input.focus();
        fetchResults("");
    }

    function closePalette() {
        overlay.classList.remove("is-open");
        overlay.hidden = true;
    }

    function renderResults(items) {
        list.innerHTML = "";
        if (!items.length) {
            list.innerHTML = '<li class="pa-palette__empty">Ничего не найдено</li>';
            return;
        }
        items.forEach(function (item, idx) {
            var li = document.createElement("li");
            li.className = "pa-palette__item" + (idx === 0 ? " is-active" : "");
            li.dataset.url = item.url || "#";
            li.innerHTML =
                '<span class="pa-palette__type">' + (item.type || "") + "</span>" +
                '<span class="pa-palette__title">' + (item.title || "") + "</span>" +
                '<span class="pa-palette__sub">' + (item.subtitle || "") + "</span>";
            li.addEventListener("click", function () {
                if (item.url) window.location.href = item.url;
            });
            list.appendChild(li);
        });
    }

    function fetchResults(q) {
        var url = "/platform-admin/api/search/?q=" + encodeURIComponent(q);
        fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
            .then(function (r) { return r.json(); })
            .then(function (data) { renderResults(data.results || []); })
            .catch(function () { list.innerHTML = '<li class="pa-palette__empty">Ошибка поиска</li>'; });
    }

    function activeItem() {
        return list.querySelector(".pa-palette__item.is-active");
    }

    function moveActive(dir) {
        var items = list.querySelectorAll(".pa-palette__item");
        if (!items.length) return;
        var idx = 0;
        items.forEach(function (el, i) {
            if (el.classList.contains("is-active")) idx = i;
            el.classList.remove("is-active");
        });
        idx = (idx + dir + items.length) % items.length;
        items[idx].classList.add("is-active");
        items[idx].scrollIntoView({ block: "nearest" });
    }

    document.addEventListener("keydown", function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
            e.preventDefault();
            openPalette();
            return;
        }
        if (!overlay.classList.contains("is-open")) return;
        if (e.key === "Escape") {
            e.preventDefault();
            closePalette();
        } else if (e.key === "ArrowDown") {
            e.preventDefault();
            moveActive(1);
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            moveActive(-1);
        } else if (e.key === "Enter") {
            var el = activeItem();
            if (el && el.dataset.url) window.location.href = el.dataset.url;
        }
    });

    input.addEventListener("input", function () {
        clearTimeout(timer);
        var q = input.value;
        timer = setTimeout(function () { fetchResults(q); }, 180);
    });

    overlay.addEventListener("click", function (e) {
        if (e.target === overlay) closePalette();
    });

    var btn = document.getElementById("paPaletteOpen");
    if (btn) btn.addEventListener("click", openPalette);
})();
