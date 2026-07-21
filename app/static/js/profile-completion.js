(function (global) {
    var DEFAULT_META = {
        has_photo: false,
        services_active: 0,
        services_total: 0,
        calendars_active: 0,
        calendars_total: 0,
        about_min_chars: 30,
        about_full_chars: 80,
        social_links_for_full: 2,
        social_fields: [
            'social_instagram',
            'social_facebook',
            'social_vk',
            'social_telegram',
            'social_youtube',
            'website',
        ],
    };

    function text(value) {
        var t = (value || '').trim();
        if (t.toLowerCase() === 'none' || t.toLowerCase() === 'null') return '';
        return t;
    }

    function aboutPoints(description, meta) {
        var length = text(description).length;
        var minChars = meta.about_min_chars || 30;
        var fullChars = meta.about_full_chars || 80;
        if (length >= fullChars) {
            return { points: 20, done: true, label: 'Описание (' + length + ' симв.)' };
        }
        if (length >= minChars) {
            return {
                points: 10,
                done: false,
                label: 'Описание (' + length + ' из ' + fullChars + ' симв.)',
                partial: true,
            };
        }
        return { points: 0, done: false, label: 'Описание (от ' + minChars + ' симв.)' };
    }

    function socialPoints(formData, meta) {
        var count = 0;
        (meta.social_fields || []).forEach(function (field) {
            if (text(formData[field])) count += 1;
        });
        var need = meta.social_links_for_full || 2;
        if (count >= need) {
            return {
                points: 15,
                done: true,
                label: 'Соцсети (' + count + ' из ' + (meta.social_fields || []).length + ')',
            };
        }
        if (count === 1) {
            return {
                points: 8,
                done: false,
                partial: true,
                label: 'Соцсети (1 из ' + need + ', нужна ещё 1)',
            };
        }
        return { points: 0, done: false, label: 'Соцсети (0 из ' + need + ')' };
    }

    function completionMessage(percent) {
        if (percent >= 90) return 'Профиль готов для клиентов';
        if (percent >= 70) return 'Профиль почти готов';
        if (percent >= 40) return 'Хороший старт — добавьте ещё несколько блоков';
        return 'Заполните профиль, чтобы клиентам было проще записаться';
    }

    function computeFromForm(formData, meta) {
        meta = meta || DEFAULT_META;
        formData = formData || {};
        var checks = [];
        var score = 0;

        var nameOk = text(formData.first_name) && text(formData.last_name);
        var namePoints = nameOk ? 10 : 0;
        score += namePoints;
        checks.push({
            id: 'name',
            label: 'Имя и фамилия',
            tab: 'basic',
            weight: 10,
            points: namePoints,
            done: nameOk,
        });

        var contactsOk = text(formData.email) && text(formData.phone);
        var contactsPoints = contactsOk ? 10 : 0;
        score += contactsPoints;
        checks.push({
            id: 'contacts',
            label: 'Email и телефон',
            tab: 'basic',
            weight: 10,
            points: contactsPoints,
            done: contactsOk,
        });

        var hasPhoto = !!meta.has_photo;
        var photoPoints = hasPhoto ? 15 : 0;
        score += photoPoints;
        checks.push({
            id: 'photo',
            label: 'Фото профиля',
            tab: 'photo',
            weight: 15,
            points: photoPoints,
            done: hasPhoto,
        });

        var about = aboutPoints(formData.profile_description, meta);
        score += about.points;
        checks.push({
            id: 'about',
            label: about.label,
            tab: 'about',
            weight: 20,
            points: about.points,
            done: about.done,
            partial: !!about.partial,
        });

        var videoOk = text(formData.video_link);
        var videoPoints = videoOk ? 5 : 0;
        score += videoPoints;
        checks.push({
            id: 'video',
            label: 'Видео-презентация',
            tab: 'video',
            weight: 5,
            points: videoPoints,
            done: !!videoOk,
        });

        var social = socialPoints(formData, meta);
        score += social.points;
        checks.push({
            id: 'social',
            label: social.label,
            tab: 'social',
            weight: 15,
            points: social.points,
            done: social.done,
            partial: !!social.partial,
        });

        var servicesActive = meta.services_active || 0;
        var servicesTotal = meta.services_total || 0;
        var servicesDone = servicesActive > 0;
        var servicesPoints = servicesDone ? 15 : 0;
        score += servicesPoints;
        checks.push({
            id: 'services',
            label: 'Активные услуги (' + servicesActive + ' из ' + servicesTotal + ')',
            tab: null,
            weight: 15,
            points: servicesPoints,
            done: servicesDone,
        });

        var calendarsActive = meta.calendars_active || 0;
        var calendarsTotal = meta.calendars_total || 0;
        var calendarDone = calendarsActive > 0;
        var calendarPoints = calendarDone ? 10 : 0;
        score += calendarPoints;
        checks.push({
            id: 'calendar',
            label: 'Активный календарь (' + calendarsActive + ' из ' + calendarsTotal + ')',
            tab: null,
            weight: 10,
            points: calendarPoints,
            done: calendarDone,
        });

        var percent = Math.min(score, 100);
        return {
            percent: percent,
            message: completionMessage(percent),
            checks: checks,
            missing: checks.filter(function (c) { return !c.done; }).map(function (c) { return c.label; }).slice(0, 4),
            total_weight: 100,
        };
    }

    function applyCompleteness(comp, dash) {
        if (!comp) return;
        var percent = comp.percent != null ? comp.percent : 0;

        document.querySelectorAll('[data-dash]').forEach(function (el) {
            var key = el.getAttribute('data-dash');
            if (key === 'completeness') {
                el.textContent = percent + '%';
                return;
            }
            if (dash && dash[key] != null) {
                el.textContent = dash[key];
            }
        });

        var pct = document.getElementById('progress-percent');
        var fill = document.getElementById('progress-fill');
        var msg = document.getElementById('progress-message');
        var list = document.getElementById('progress-list');
        if (pct) pct.textContent = String(percent);
        if (fill) fill.style.width = percent + '%';
        if (msg) msg.textContent = comp.message || '';
        if (list) {
            list.innerHTML = '';
            (comp.checks || []).forEach(function (c) {
                var li = document.createElement('li');
                var stateClass = c.done ? 'is-done' : (c.partial ? 'is-partial' : 'is-missing');
                li.className = 'progress-card__item ' + stateClass;
                if (c.tab) {
                    li.dataset.tab = c.tab;
                    li.setAttribute('role', 'button');
                    li.tabIndex = 0;
                }
                var icon = c.done ? '✔' : (c.partial ? '◐' : '○');
                li.innerHTML =
                    '<span class="progress-card__item-icon">' + icon + '</span>' +
                    '<span class="progress-card__item-text">' + c.label + '</span>' +
                    '<span class="progress-card__item-points">' + (c.points || 0) + '/' + (c.weight || 0) + '</span>';
                list.appendChild(li);
            });
        }
    }

    function bindChecklistNavigation() {
        var list = document.getElementById('progress-list');
        if (!list || list.dataset.bound) return;
        list.dataset.bound = '1';
        list.addEventListener('click', function (event) {
            var item = event.target.closest('[data-tab]');
            if (!item) return;
            var tab = item.getAttribute('data-tab');
            var btn = document.querySelector('.profile-sidebar__btn[data-tab="' + tab + '"]');
            if (btn) btn.click();
        });
        list.addEventListener('keydown', function (event) {
            if (event.key !== 'Enter' && event.key !== ' ') return;
            var item = event.target.closest('[data-tab]');
            if (!item) return;
            event.preventDefault();
            item.click();
        });
    }

    function updateLive(meta) {
        if (!global.profilePreview || !global.profilePreview.collect) return;
        var formData = global.profilePreview.collect();
        var comp = computeFromForm(formData, meta || global.profileCompletionMeta || DEFAULT_META);
        applyCompleteness(comp, null);
        document.querySelectorAll('[data-dash="completeness"]').forEach(function (el) {
            el.textContent = comp.percent + '%';
        });
    }

    global.profileCompletion = {
        computeFromForm: computeFromForm,
        applyCompleteness: applyCompleteness,
        bindChecklistNavigation: bindChecklistNavigation,
        updateLive: updateLive,
    };
})(window);
