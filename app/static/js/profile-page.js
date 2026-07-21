(function () {
    function formatDate(iso) {
        if (!iso) return '—';
        try {
            var d = new Date(iso);
            return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
        } catch (e) {
            return iso;
        }
    }

    function formatRelative(iso) {
        if (!iso) return '—';
        try {
            var d = new Date(iso);
            var diff = Date.now() - d.getTime();
            var hours = Math.floor(diff / 3600000);
            if (hours < 1) return 'только что';
            if (hours < 24) return hours + ' ч. назад';
            var days = Math.floor(hours / 24);
            if (days < 7) return days + ' дн. назад';
            return formatDate(iso);
        } catch (e) {
            return iso;
        }
    }

    function applyData(data) {
        if (!data) return;
        var dash = data.dashboard || {};
        document.querySelectorAll('[data-dash]').forEach(function (el) {
            var key = el.getAttribute('data-dash');
            var val = dash[key];
            if (key === 'completeness') {
                el.textContent = (val != null ? val : 0) + '%';
            } else {
                el.textContent = val != null ? val : '—';
            }
        });
        var subServices = document.querySelector('[data-dash-sub="services_active"]');
        if (subServices) subServices.textContent = 'Активных: ' + (dash.services_active || 0);
        var subCal = document.querySelector('[data-dash-sub="calendars_active"]');
        if (subCal) subCal.textContent = 'Активных: ' + (dash.calendars_active || 0);

        var comp = data.completeness || {};
        var pct = document.getElementById('progress-percent');
        var fill = document.getElementById('progress-fill');
        var msg = document.getElementById('progress-message');
        var list = document.getElementById('progress-list');
        if (pct) pct.textContent = comp.percent || 0;
        if (fill) fill.style.width = (comp.percent || 0) + '%';
        if (msg) msg.textContent = comp.message || '';
        if (list) {
            list.innerHTML = '';
            (comp.checks || []).forEach(function (c) {
                var li = document.createElement('li');
                li.textContent = (c.done ? '✔ ' : '○ ') + c.label;
                list.appendChild(li);
            });
        }

        var profile = data.profile || {};
        var heroUpdated = document.getElementById('heroUpdated');
        if (heroUpdated) heroUpdated.textContent = 'Последнее изменение: ' + formatRelative(profile.updated_at);
        var heroSpec = document.getElementById('heroSpecialization');
        if (heroSpec && profile.specialization) heroSpec.textContent = profile.specialization;

        var heroAvatar = document.getElementById('heroAvatar');
        if (heroAvatar && profile.photo_url) {
            if (heroAvatar.tagName === 'IMG') {
                heroAvatar.src = profile.photo_url;
            }
        }

        var footer = data.footer || {};
        var map = {
            'footer-created': formatDate(footer.created_at),
            'footer-updated': formatRelative(footer.updated_at),
            'footer-id': '#' + (footer.consultant_id || '—'),
            'footer-tz': footer.timezone || '—',
            'footer-version': footer.profile_version || '—',
        };
        Object.keys(map).forEach(function (id) {
            var el = document.getElementById(id);
            if (el) el.textContent = map[id];
        });

        if (window.profilePreview) {
            window.profilePreview.applyServer(data.preview);
            window.profilePreview.update();
        }
    }

    async function init() {
        var page = document.getElementById('profile-page');
        if (!page) return;
        var csrf = page.dataset.csrf || '';
        var api = new ProfileApi(csrf);
        window.profilePage = { applyData: applyData };

        try {
            var data = await api.getData();
            applyData(data);
        } catch (e) {
            if (window.showToast) showToast('Не удалось загрузить данные профиля', 'error');
        }

        if (window.profilePreview) profilePreview.bind();
        if (window.initProfileAutosave) initProfileAutosave(api);

        document.getElementById('btn-copy-link') && document.getElementById('btn-copy-link').addEventListener('click', function () {
            if (typeof copyBookingLink === 'function') copyBookingLink(this);
        });

        document.getElementById('btn-share-profile') && document.getElementById('btn-share-profile').addEventListener('click', function () {
            if (typeof copyBookingLink === 'function') copyBookingLink(this);
        });

        document.getElementById('btn-toggle-qr') && document.getElementById('btn-toggle-qr').addEventListener('click', function () {
            var qr = document.getElementById('share-qr');
            if (qr) qr.hidden = !qr.hidden;
        });

        document.getElementById('btn-preview-mode') && document.getElementById('btn-preview-mode').addEventListener('click', function () {
            document.querySelector('.profile-mode-toggle__btn[data-mode="preview"]').click();
        });

        document.querySelectorAll('.profile-mode-toggle__btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                document.querySelectorAll('.profile-mode-toggle__btn').forEach(function (b) {
                    b.classList.toggle('is-active', b === btn);
                });
                var layout = document.getElementById('profile-layout');
                if (layout) layout.classList.toggle('is-preview-mode', btn.dataset.mode === 'preview');
            });
        });

        var drop = document.getElementById('photoDropZone');
        if (drop) {
            drop.addEventListener('dragover', function (e) {
                e.preventDefault();
                drop.classList.add('is-dragover');
            });
            drop.addEventListener('dragleave', function () {
                drop.classList.remove('is-dragover');
            });
            drop.addEventListener('drop', function (e) {
                e.preventDefault();
                drop.classList.remove('is-dragover');
                var input = document.getElementById('profilePhotoInput');
                if (input && e.dataTransfer.files.length) {
                    input.files = e.dataTransfer.files;
                    input.dispatchEvent(new Event('change'));
                }
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
