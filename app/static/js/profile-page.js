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
            var mins = Math.floor(diff / 60000);
            if (mins < 1) return 'только что';
            if (mins < 60) return mins + ' мин. назад';
            var hours = Math.floor(mins / 60);
            if (hours < 24) return hours + ' ч. назад';
            var days = Math.floor(hours / 24);
            if (days < 7) return days + ' дн. назад';
            return formatDate(iso);
        } catch (e) {
            return iso;
        }
    }

    function loadJson(id) {
        var node = document.getElementById(id);
        if (!node) return null;
        try {
            return JSON.parse(node.textContent || 'null');
        } catch (e) {
            console.error('[profile] Failed to parse JSON:', id, e);
            return null;
        }
    }

    function dashValue(val) {
        return val != null && val !== '' ? val : '0';
    }

    function updateHeroStats(dash, completeness) {
        var services = document.querySelector('[data-hero-stat="services"]');
        var clients = document.querySelector('[data-hero-stat="clients"]');
        var comp = document.querySelector('[data-hero-stat="completeness"]');
        if (services) services.textContent = dashValue(dash.services_total);
        if (clients) clients.textContent = dashValue(dash.clients_total);
        if (comp) comp.textContent = completeness != null ? completeness : dashValue(dash.completeness);
    }

    function applyData(data) {
        if (!data) return;
        var dash = data.dashboard || {};
        document.querySelectorAll('[data-dash]').forEach(function (el) {
            var key = el.getAttribute('data-dash');
            if (key === 'completeness') {
                var pct = data.completeness ? data.completeness.percent : dash.completeness;
                el.textContent = dashValue(pct) + '%';
                return;
            }
            el.textContent = dashValue(dash[key]);
        });
        var subServices = document.querySelector('[data-dash-sub="services_active"]');
        if (subServices) subServices.textContent = 'Активных: ' + dashValue(dash.services_active);
        var subCal = document.querySelector('[data-dash-sub="calendars_active"]');
        if (subCal) subCal.textContent = 'Активных: ' + dashValue(dash.calendars_active);

        if (data.completion_meta) {
            window.profileCompletionMeta = data.completion_meta;
        }

        if (window.profileCompletion) {
            profileCompletion.applyCompleteness(data.completeness || {}, dash);
            profileCompletion.bindChecklistNavigation();
        }

        updateHeroStats(dash, data.completeness ? data.completeness.percent : null);

        var profile = data.profile || {};
        var heroUpdated = document.getElementById('heroUpdated');
        if (heroUpdated) {
            heroUpdated.textContent = 'Последнее изменение: ' + formatRelative(profile.updated_at);
        }
        var heroSpec = document.getElementById('heroSpecialization');
        if (heroSpec && profile.specialization) heroSpec.textContent = profile.specialization;

        if (window.profilePreview) {
            window.profilePreview.setAvatars(
                profile.photo_url || null,
                profile.first_name,
                profile.last_name
            );
            window.profilePreview.applyServer(data.preview);
            window.profilePreview.update();
        }

        var footer = data.footer || {};
        var map = {
            'footer-created': formatDate(footer.created_at),
            'footer-updated': formatRelative(footer.updated_at),
            'footer-id': footer.consultant_id ? '#' + footer.consultant_id : '—',
            'footer-tz': footer.timezone || '—',
            'footer-version': footer.profile_version || '—',
        };
        Object.keys(map).forEach(function (id) {
            var el = document.getElementById(id);
            if (el) el.textContent = map[id];
        });
    }

    async function init() {
        var page = document.getElementById('profile-page');
        if (!page) return;
        var csrf = page.dataset.csrf || '';
        var api = new ProfileApi(csrf);
        window.profilePage = { applyData: applyData };
        window.profileCompletionMeta = loadJson('profile-completion-meta') || {};

        var initialData = loadJson('profile-initial-data');
        if (initialData) {
            applyData(initialData);
        }

        if (window.profileCompletion) {
            profileCompletion.bindChecklistNavigation();
        }

        try {
            var data = await api.getData();
            applyData(data);
        } catch (e) {
            console.error('[profile] API load failed, using server-rendered data:', e);
            if (window.profileCompletion && window.profilePreview) {
                profileCompletion.updateLive(window.profileCompletionMeta);
            }
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
