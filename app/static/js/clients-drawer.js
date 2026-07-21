(function (global) {
    var clientsIndex = {};

    function findClient(id) {
        return clientsIndex[id] || null;
    }

    function renderDrawer(client) {
        var body = document.getElementById('client-drawer-body');
        var title = document.getElementById('client-drawer-title');
        var fullLink = document.getElementById('client-drawer-open-full');
        if (!body || !client) return;

        if (title) title.textContent = client.name;
        if (fullLink) fullLink.href = client.detail_url;

        var comp = client.completeness || { percent: 0, missing: [] };
        var missingHtml = (comp.missing || []).map(function (m) {
            return '<li>Добавьте ' + m + '</li>';
        }).join('');

        body.innerHTML =
            '<div class="drawer-profile">' +
            '<div class="drawer-profile__avatar" style="background:' + client.avatar_color + '">' + client.initials + '</div>' +
            '<h3 class="drawer-profile__name">' + client.name + '</h3>' +
            (client.badge_label ? '<span class="client-card__badge client-card__badge--' + client.badge + '">' + client.badge_label + '</span>' : '') +
            '</div>' +
            '<section class="drawer-section"><h4 class="drawer-section__title">Контакты</h4>' +
            '<ul class="drawer-contacts">' +
            (client.phone ? '<li>📞 ' + client.phone + '</li>' : '') +
            (client.email ? '<li>✉ ' + client.email + '</li>' : '') +
            (client.telegram ? '<li>✈ ' + client.telegram + '</li>' : '') +
            (!client.phone && !client.email && !client.telegram ? '<li>Контакты не указаны</li>' : '') +
            '</ul></section>' +
            (client.notes ? '<section class="drawer-section"><h4 class="drawer-section__title">Заметки</h4><p>' + client.notes.replace(/</g, '&lt;') + '</p></section>' : '') +
            '<section class="drawer-section drawer-completeness">' +
            '<h4 class="drawer-section__title">Заполненность карточки — ' + comp.percent + '%</h4>' +
            '<div class="drawer-completeness__bar"><div class="drawer-completeness__fill" style="width:' + comp.percent + '%"></div></div>' +
            (missingHtml ? '<ul class="drawer-completeness__missing">' + missingHtml + '</ul>' : '<p class="text-muted text-body-sm">Карточка заполнена полностью</p>') +
            '</section>' +
            '<section class="drawer-section"><h4 class="drawer-section__title">Статистика</h4>' +
            '<p class="text-body-sm">Записей: <strong>' + (client.booking_count || 0) + '</strong></p>' +
            '</section>' +
            '<p class="text-body-sm text-muted">Здесь в будущих версиях появятся история посещений, заметки, документы и задачи.</p>';
    }

    function open(id) {
        var drawer = document.getElementById('client-drawer');
        var client = findClient(id);
        if (!drawer || !client) return;
        renderDrawer(client);
        drawer.hidden = false;
        drawer.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';
    }

    function close() {
        var drawer = document.getElementById('client-drawer');
        if (!drawer) return;
        drawer.hidden = true;
        drawer.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = '';
    }

    function init(clients) {
        clientsIndex = {};
        (clients || []).forEach(function (c) {
            clientsIndex[c.id] = c;
        });

        document.querySelectorAll('[data-open-drawer]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                open(parseInt(btn.getAttribute('data-open-drawer'), 10));
            });
        });

        document.getElementById('client-drawer-close') && document.getElementById('client-drawer-close').addEventListener('click', close);
        document.getElementById('client-drawer-backdrop') && document.getElementById('client-drawer-backdrop').addEventListener('click', close);

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') close();
        });
    }

    global.clientDrawer = { init: init, open: open, close: close };
})(window);
