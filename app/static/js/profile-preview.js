(function (global) {
    function videoEmbed(url) {
        if (!url) return '';
        var u = url.trim();
        var yt = u.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([\w-]+)/i);
        if (yt) return '<iframe src="https://www.youtube.com/embed/' + yt[1] + '" allowfullscreen loading="lazy"></iframe>';
        var vk = u.match(/vk\.com\/video(-?\d+_\d+)/i);
        if (vk) return '<iframe src="https://vk.com/video_ext.php?oid=' + vk[1].split('_')[0] + '&id=' + vk[1].split('_')[1] + '" allowfullscreen loading="lazy"></iframe>';
        var rutube = u.match(/rutube\.ru\/video\/([\w-]+)/i);
        if (rutube) return '<iframe src="https://rutube.ru/play/embed/' + rutube[1] + '" allowfullscreen loading="lazy"></iframe>';
        return '<a href="' + u + '" target="_blank" rel="noopener">Открыть видео</a>';
    }

    function collectFormData() {
        var form = document.getElementById('profileForm');
        if (!form) return {};
        var data = {};
        form.querySelectorAll('.profile-field').forEach(function (el) {
            if (el.name) data[el.name] = el.value;
        });
        return data;
    }

    function updatePreviewFromForm() {
        var first = document.getElementById('first_name');
        var last = document.getElementById('last_name');
        var desc = document.getElementById('profile_description');
        var nameEl = document.getElementById('preview-name');
        var descEl = document.getElementById('preview-desc');
        var heroName = document.getElementById('heroName');
        if (nameEl && first && last) {
            var name = (first.value + ' ' + last.value).trim();
            nameEl.textContent = name || 'Специалист';
            if (heroName) heroName.textContent = name || 'Специалист';
        }
        if (descEl && desc) descEl.textContent = desc.value || 'Добавьте описание профиля';
        updateSocialPreview();
        updateVideoPreview();
        updateDescCount();
    }

    function updateDescCount() {
        var desc = document.getElementById('profile_description');
        var counter = document.getElementById('desc-count');
        if (desc && counter) counter.textContent = (desc.value || '').length;
    }

    function updateSocialPreview() {
        var wrap = document.getElementById('preview-social');
        if (!wrap) return;
        var map = [
            ['social_telegram', 'TG'],
            ['social_vk', 'VK'],
            ['social_instagram', 'IG'],
            ['social_youtube', 'YT'],
            ['website', 'Web'],
        ];
        wrap.innerHTML = '';
        map.forEach(function (item) {
            var el = document.getElementById(item[0]);
            if (el && el.value.trim()) {
                var a = document.createElement('a');
                a.href = el.value.trim();
                a.target = '_blank';
                a.rel = 'noopener';
                a.textContent = item[1];
                wrap.appendChild(a);
            }
        });
        document.querySelectorAll('[data-social-status]').forEach(function (badge) {
            var field = badge.getAttribute('data-social-status');
            var input = document.getElementById(field);
            if (!input) return;
            if (input.value.trim()) {
                badge.textContent = 'Подключен';
                badge.classList.add('is-connected');
            } else {
                badge.textContent = 'Не подключен';
                badge.classList.remove('is-connected');
            }
        });
    }

    function updateVideoPreview() {
        var input = document.getElementById('video_link');
        var panel = document.getElementById('video-preview');
        var previewPanel = document.getElementById('preview-video');
        if (!input) return;
        var html = videoEmbed(input.value);
        if (panel) {
            panel.innerHTML = html;
            panel.hidden = !input.value.trim();
        }
        if (previewPanel) {
            previewPanel.innerHTML = html;
            previewPanel.hidden = !input.value.trim();
        }
    }

    function applyServerPreview(preview) {
        if (!preview) return;
        var avatar = document.getElementById('preview-avatar');
        var spec = document.getElementById('preview-spec');
        var services = document.getElementById('preview-services');
        if (avatar) {
            if (preview.photo_url) {
                avatar.style.backgroundImage = 'url(' + preview.photo_url + ')';
            } else {
                avatar.style.backgroundImage = '';
            }
        }
        if (spec) spec.textContent = preview.specialization || '';
        if (services) {
            services.innerHTML = '';
            (preview.services || []).forEach(function (s) {
                var li = document.createElement('li');
                li.textContent = s.name;
                li.style.setProperty('--svc-color', s.color || '#7d5cff');
                services.appendChild(li);
            });
        }
    }

    function bindLivePreview() {
        document.querySelectorAll('.profile-field').forEach(function (el) {
            el.addEventListener('input', updatePreviewFromForm);
            el.addEventListener('change', updatePreviewFromForm);
        });
        updatePreviewFromForm();
    }

    global.profilePreview = {
        bind: bindLivePreview,
        update: updatePreviewFromForm,
        applyServer: applyServerPreview,
        collect: collectFormData,
        videoEmbed: videoEmbed,
    };
})(window);
