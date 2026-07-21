/**
 * Circular avatar crop editor for profile photo upload.
 * Accepts common image formats; outputs a square JPEG for the circular preview.
 */
(function () {
    var input = document.getElementById('profilePhotoInput');
    var modal = document.getElementById('avatarCropModal');
    var canvas = document.getElementById('avatarCropCanvas');
    var preview = document.getElementById('avatarCropPreview');
    var applyBtn = document.getElementById('avatarCropApply');
    var cancelBtn = document.getElementById('avatarCropCancel');
    var zoom = document.getElementById('avatarCropZoom');
    var hint = document.getElementById('avatarCropHint');
    var form = document.getElementById('profileForm');
    if (!input || !modal || !canvas) return;

    var profilePreview = document.getElementById('profilePhotoPreview');
    var ctx = canvas.getContext('2d');
    var img = new Image();
    var scale = 1;
    var offsetX = 0;
    var offsetY = 0;
    var dragging = false;
    var lastX = 0;
    var lastY = 0;
    var pendingBlob = null;
    var previewObjectUrl = null;
    var SIZE = 320;
    canvas.width = SIZE;
    canvas.height = SIZE;

    function revokePreviewUrl() {
        if (previewObjectUrl) {
            URL.revokeObjectURL(previewObjectUrl);
            previewObjectUrl = null;
        }
    }

    function openModal() {
        modal.hidden = false;
        modal.classList.add('is-open');
    }

    function closeModal(clearInput) {
        modal.hidden = true;
        modal.classList.remove('is-open');
        if (clearInput) {
            input.value = '';
            pendingBlob = null;
        }
    }

    function isAllowedImage(file) {
        var name = (file.name || '').toLowerCase();
        var okExt = /\.(jpe?g|png|webp)$/i.test(name) || !name.includes('.');
        var okType = !file.type || file.type === 'image/jpeg' || file.type === 'image/png' || file.type === 'image/webp';
        return okExt && okType;
    }

    function updateProfilePreview(blob) {
        if (!profilePreview || !blob) return;
        revokePreviewUrl();
        previewObjectUrl = URL.createObjectURL(blob);
        if (profilePreview.tagName === 'IMG') {
            profilePreview.src = previewObjectUrl;
        } else {
            var image = document.createElement('img');
            image.src = previewObjectUrl;
            image.alt = 'Фото профиля';
            image.className = 'profile-photo';
            image.id = 'profilePhotoPreview';
            profilePreview.replaceWith(image);
            profilePreview = image;
        }
    }

    function assignFileToInput(blob) {
        var file = new File([blob], 'photo.jpg', { type: 'image/jpeg' });
        try {
            var dt = new DataTransfer();
            dt.items.add(file);
            input.files = dt.files;
            return !!(input.files && input.files.length);
        } catch (err) {
            return false;
        }
    }

    function draw() {
        ctx.clearRect(0, 0, SIZE, SIZE);
        ctx.fillStyle = '#0b1020';
        ctx.fillRect(0, 0, SIZE, SIZE);
        if (!img.naturalWidth) return;
        var base = Math.max(SIZE / img.naturalWidth, SIZE / img.naturalHeight);
        var s = base * scale;
        var w = img.naturalWidth * s;
        var h = img.naturalHeight * s;
        var x = (SIZE - w) / 2 + offsetX;
        var y = (SIZE - h) / 2 + offsetY;
        ctx.drawImage(img, x, y, w, h);
        ctx.save();
        ctx.beginPath();
        ctx.arc(SIZE / 2, SIZE / 2, SIZE / 2 - 2, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(73, 209, 255, 0.9)';
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.restore();
        if (preview) {
            preview.style.backgroundImage = 'url(' + canvas.toDataURL('image/jpeg', 0.92) + ')';
        }
    }

    function loadFile(file) {
        if (!isAllowedImage(file)) {
            if (hint) hint.textContent = 'Допустимы только JPG, PNG или WEBP';
            input.value = '';
            return;
        }
        var reader = new FileReader();
        reader.onload = function () {
            img.onload = function () {
                scale = 1;
                offsetX = 0;
                offsetY = 0;
                if (zoom) zoom.value = '1';
                openModal();
                draw();
            };
            img.onerror = function () {
                if (hint) hint.textContent = 'Не удалось открыть изображение. Попробуйте JPG или PNG.';
                input.value = '';
            };
            img.src = reader.result;
        };
        reader.readAsDataURL(file);
    }

    function submitWithBlob(blob) {
        if (!form) return;
        var file = new File([blob], 'photo.jpg', { type: 'image/jpeg' });
        var fd = new FormData(form);
        fd.delete('profile_photo');
        fd.append('profile_photo', file, 'photo.jpg');
        fetch(form.action, {
            method: 'POST',
            body: fd,
            credentials: 'same-origin',
        }).then(function (response) {
            if (response.ok) {
                window.location.reload();
                return;
            }
            window.location.reload();
        }).catch(function () {
            assignFileToInput(blob);
            form.submit();
        });
    }

    input.addEventListener('change', function () {
        if (!input.files || !input.files[0]) return;
        pendingBlob = null;
        loadFile(input.files[0]);
    });

    if (zoom) {
        zoom.addEventListener('input', function () {
            scale = parseFloat(zoom.value) || 1;
            draw();
        });
    }

    canvas.addEventListener('pointerdown', function (e) {
        dragging = true;
        lastX = e.clientX;
        lastY = e.clientY;
        canvas.setPointerCapture(e.pointerId);
    });
    canvas.addEventListener('pointermove', function (e) {
        if (!dragging) return;
        offsetX += e.clientX - lastX;
        offsetY += e.clientY - lastY;
        lastX = e.clientX;
        lastY = e.clientY;
        draw();
    });
    canvas.addEventListener('pointerup', function () { dragging = false; });
    canvas.addEventListener('pointercancel', function () { dragging = false; });

    if (cancelBtn) cancelBtn.addEventListener('click', function () { closeModal(true); });
    modal.addEventListener('click', function (e) {
        if (e.target === modal) closeModal(true);
    });

    if (applyBtn) {
        applyBtn.addEventListener('click', function () {
            var out = document.createElement('canvas');
            out.width = 512;
            out.height = 512;
            var octx = out.getContext('2d');
            var base = Math.max(SIZE / img.naturalWidth, SIZE / img.naturalHeight);
            var s = base * scale * (512 / SIZE);
            var w = img.naturalWidth * s;
            var h = img.naturalHeight * s;
            var x = (512 - w) / 2 + offsetX * (512 / SIZE);
            var y = (512 - h) / 2 + offsetY * (512 / SIZE);
            octx.fillStyle = '#0b1020';
            octx.fillRect(0, 0, 512, 512);
            octx.drawImage(img, x, y, w, h);
            out.toBlob(function (blob) {
                if (!blob) return;
                pendingBlob = blob;
                updateProfilePreview(blob);
                assignFileToInput(blob);
                closeModal(false);
                if (hint) hint.textContent = 'Фото готово. Нажмите «Сохранить профиль».';
            }, 'image/jpeg', 0.92);
        });
    }

    if (form) {
        form.addEventListener('submit', function (e) {
            if (!pendingBlob) return;
            if (!input.files || !input.files.length) {
                e.preventDefault();
                submitWithBlob(pendingBlob);
                return;
            }
            assignFileToInput(pendingBlob);
            if (!input.files || !input.files.length) {
                e.preventDefault();
                submitWithBlob(pendingBlob);
            }
        });
    }
})();
