(function (global) {
    var SOCIAL_CONFIG = [
        { field: 'social_telegram', label: 'Telegram', icon: '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>' },
        { field: 'social_vk', label: 'VK', icon: '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M15.684 0H8.316C1.592 0 0 1.592 0 8.316v7.368C0 22.408 1.592 24 8.316 24h7.368C22.408 24 24 22.408 24 15.684V8.316C24 1.592 22.391 0 15.684 0zm3.692 17.123h-1.744c-.66 0-.862-.525-2.049-1.727-1.033-1-1.49-1.135-1.744-1.135-.356 0-.458.102-.458.593v1.575c0 .424-.135.678-1.253.678-1.846 0-3.896-1.118-5.335-3.202C4.624 10.857 4 8.657 4 8.096c0-.254.102-.491.593-.491h1.744c.44 0 .61.203.78.677.863 2.49 2.303 4.675 2.896 4.675.22 0 .322-.102.322-.66V9.721c-.068-1.186-.695-1.287-.695-1.71 0-.203.17-.407.44-.407h2.744c.373 0 .508.203.508.643v3.49c0 .372.17.508.271.508.22 0 .407-.136.813-.542 1.254-1.406 2.151-3.574 2.151-3.574.119-.254.322-.491.762-.491h1.744c.525 0 .644.27.525.643-.22 1.017-2.354 4.031-2.354 4.031-.186.305-.254.44 0 .78.186.254.796.779 1.203 1.253.745.847 1.32 1.558 1.473 2.049.17.474-.085.72-.576.72z"/></svg>' },
        { field: 'social_instagram', label: 'Instagram', icon: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="20" rx="5"/><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"/><line x1="17.5" y1="6.5" x2="17.51" y2="6.5"/></svg>' },
        { field: 'social_youtube', label: 'YouTube', icon: '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>' },
        { field: 'website', label: 'Сайт', icon: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>', slug: 'website' },
    ];

    function socialSlug(item) {
        if (item.slug) return item.slug;
        return (item.field || '').replace(/^social_/, '');
    }

    function socialHref(raw) {
        var url = (raw || '').trim();
        if (!url) return '';
        if (/^https?:\/\//i.test(url)) return url;
        if (/^\/\//.test(url)) return 'https:' + url;
        return 'https://' + url.replace(/^\/+/, '');
    }

    function renderSocialBar(container) {
        if (!container) return;
        container.innerHTML = '';
        SOCIAL_CONFIG.forEach(function (item) {
            var input = document.getElementById(item.field);
            var url = input && input.value.trim();
            var slug = socialSlug(item);
            var node;
            if (url) {
                node = document.createElement('a');
                node.href = socialHref(url);
                node.target = '_blank';
                node.rel = 'noopener';
            } else {
                node = document.createElement('span');
                node.setAttribute('aria-disabled', 'true');
            }
            node.className = 'pp-social__btn pp-social__btn--' + slug + (url ? ' is-active' : ' is-inactive');
            node.title = url ? item.label : item.label + ' — ссылка не указана';
            node.innerHTML = item.icon;
            container.appendChild(node);
        });
    }

    function videoEmbedHtml(url) {
        if (!url) return '';
        var u = url.trim();
        var yt = u.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([\w-]+)/i);
        if (yt) return '<iframe src="https://www.youtube.com/embed/' + yt[1] + '" allowfullscreen loading="lazy" title="Видео"></iframe>';
        var vk = u.match(/vk\.com\/video(-?\d+_\d+)/i);
        if (vk) return '<iframe src="https://vk.com/video_ext.php?oid=' + vk[1].split('_')[0] + '&id=' + vk[1].split('_')[1] + '" allowfullscreen loading="lazy" title="Видео"></iframe>';
        var rutube = u.match(/rutube\.ru\/video\/([\w-]+)/i);
        if (rutube) return '<iframe src="https://rutube.ru/play/embed/' + rutube[1] + '" allowfullscreen loading="lazy" title="Видео"></iframe>';
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

    function getInitials(first, last) {
        var a = (first || '').trim();
        var b = (last || '').trim();
        if (a && b) return (a[0] + b[0]).toUpperCase();
        return (a || b || '?')[0].toUpperCase();
    }

    function setAvatarElement(el, photoUrl, initials) {
        if (!el) return;
        var parent = el.parentNode;
        if (!parent) return;
        var isEditor = el.id === 'profilePhotoPreview';
        var isPreview = el.id === 'preview-avatar';
        var isHero = el.id === 'heroAvatar';
        if (photoUrl) {
            if (el.tagName === 'IMG') {
                el.src = photoUrl;
                el.classList.remove('pp-avatar--empty', 'profile-hero__avatar--empty', 'profile-photo--empty');
            } else {
                var img = document.createElement('img');
                img.id = el.id;
                if (isPreview) {
                    img.className = 'pp-avatar';
                } else if (isHero) {
                    img.className = 'profile-hero__avatar';
                } else if (isEditor) {
                    img.className = 'profile-photo profile-photo--large';
                    img.alt = 'Фото';
                } else {
                    img.className = el.className.replace(/\s*--empty/g, '');
                }
                img.alt = '';
                img.dataset.avatarRole = 'photo';
                img.src = photoUrl;
                parent.replaceChild(img, el);
            }
        } else {
            var text = initials || '?';
            if (el.tagName === 'IMG') {
                var div = document.createElement('div');
                div.id = el.id;
                if (isPreview) {
                    div.className = 'pp-avatar pp-avatar--empty';
                } else if (isHero) {
                    div.className = 'profile-hero__avatar profile-hero__avatar--empty';
                } else if (isEditor) {
                    div.className = 'profile-photo profile-photo--large profile-photo--empty';
                    div.textContent = 'Нет фото';
                } else {
                    div.className = el.className + ' --empty';
                }
                div.dataset.avatarRole = 'initials';
                if (!isEditor) div.textContent = text;
                parent.replaceChild(div, el);
            } else if (!isEditor) {
                el.textContent = text;
            }
        }
    }

    function updateAllAvatars(photoUrl, first, last) {
        var initials = getInitials(first, last);
        setAvatarElement(document.getElementById('heroAvatar'), photoUrl, initials);
        setAvatarElement(document.getElementById('preview-avatar'), photoUrl, initials);
        var editorPhoto = document.getElementById('profilePhotoPreview');
        if (editorPhoto) {
            setAvatarElement(editorPhoto, photoUrl, initials);
        }
        if (global.profileCompletionMeta) {
            global.profileCompletionMeta.has_photo = !!photoUrl;
        }
    }

    function updatePreviewFromForm() {
        var first = document.getElementById('first_name');
        var last = document.getElementById('last_name');
        var desc = document.getElementById('profile_description');
        var specInput = document.getElementById('heroSpecialization');
        var nameEl = document.getElementById('preview-name');
        var specEl = document.getElementById('preview-spec');
        var roleEl = document.getElementById('preview-role');
        var descEl = document.getElementById('preview-desc');
        var heroName = document.getElementById('heroName');
        var name = ((first && first.value) || '') + ' ' + ((last && last.value) || '');
        name = name.trim() || 'Специалист';
        if (nameEl) nameEl.textContent = name;
        if (heroName) heroName.textContent = name;
        var specText = specInput ? specInput.textContent.trim() : 'Специалист';
        if (specEl) specEl.textContent = specText;
        if (roleEl) roleEl.textContent = specText;
        if (descEl) {
            var val = (desc && desc.value || '').trim();
            if (val) {
                descEl.textContent = val;
                descEl.classList.remove('is-empty');
            } else {
                descEl.innerHTML = '<span class="pp-desc__empty">Описание пока не заполнено. Расскажите клиентам о себе и своих услугах.</span>';
                descEl.classList.add('is-empty');
            }
        }
        updateSocialPreview();
        updateVideoPreview();
        updateDescCount();
        if (global.profileCompletion) {
            global.profileCompletion.updateLive(global.profileCompletionMeta);
        }
    }

    function updateDescCount() {
        var desc = document.getElementById('profile_description');
        var counter = document.getElementById('desc-count');
        if (desc && counter) counter.textContent = (desc.value || '').length;
    }

    function updateSocialPreview() {
        renderSocialBar(document.getElementById('preview-social'));
        renderSocialBar(document.getElementById('social-icons-bar'));
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
        var card = document.getElementById('preview-video-card');
        var embed = document.getElementById('preview-video');
        if (!input) return;
        var hasUrl = !!input.value.trim();
        var html = videoEmbedHtml(input.value);
        if (panel) {
            panel.innerHTML = hasUrl ? html : '';
            panel.hidden = !hasUrl;
        }
        if (card) card.hidden = !hasUrl;
        if (embed) {
            embed.innerHTML = '';
            embed.hidden = true;
        }
    }

    function bindVideoCard() {
        var trigger = document.getElementById('preview-video-trigger');
        var embed = document.getElementById('preview-video');
        var input = document.getElementById('video_link');
        if (!trigger || !embed || !input || trigger.dataset.bound) return;
        trigger.dataset.bound = '1';
        trigger.addEventListener('click', function () {
            if (!input.value.trim()) return;
            embed.innerHTML = videoEmbedHtml(input.value);
            embed.hidden = !embed.hidden;
            trigger.hidden = !embed.hidden;
        });
    }

    function applyServerPreview(preview) {
        if (!preview) return;
        var first = document.getElementById('first_name');
        var last = document.getElementById('last_name');
        updateAllAvatars(
            preview.photo_url || null,
            preview.full_name ? preview.full_name.split(' ')[0] : (first && first.value),
            preview.full_name ? preview.full_name.split(' ').slice(1).join(' ') : (last && last.value)
        );
        var spec = document.getElementById('preview-spec');
        var role = document.getElementById('preview-role');
        if (spec) spec.textContent = preview.specialization || '';
        if (role) role.textContent = preview.specialization || '';
        var services = document.getElementById('preview-services');
        if (services) {
            services.innerHTML = '';
            (preview.services || []).forEach(function (s) {
                var li = document.createElement('li');
                li.className = 'pp-services__item';
                li.innerHTML = '<span class="pp-services__dot"></span><span>' + s.name + '</span>';
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
        bindVideoCard();
        updatePreviewFromForm();
    }

    global.profilePreview = {
        bind: bindLivePreview,
        update: updatePreviewFromForm,
        applyServer: applyServerPreview,
        collect: collectFormData,
        setAvatars: updateAllAvatars,
        videoEmbed: videoEmbedHtml,
    };
})(window);
