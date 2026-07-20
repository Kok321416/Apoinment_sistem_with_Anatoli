/**
 * Circular avatar crop editor for profile photo upload.
 * Accepts JPG/PNG only; outputs a square JPEG for the circular preview.
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
    if (!input || !modal || !canvas) return;

    var ctx = canvas.getContext('2d');
    var img = new Image();
    var scale = 1;
    var offsetX = 0;
    var offsetY = 0;
    var dragging = false;
    var lastX = 0;
    var lastY = 0;
    var SIZE = 320;
    canvas.width = SIZE;
    canvas.height = SIZE;

    function openModal() {
        modal.hidden = false;
        modal.classList.add('is-open');
    }

    function closeModal() {
        modal.hidden = true;
        modal.classList.remove('is-open');
        input.value = '';
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
        var name = (file.name || '').toLowerCase();
        var okExt = name.endsWith('.jpg') || name.endsWith('.jpeg') || name.endsWith('.png');
        var okType = file.type === 'image/jpeg' || file.type === 'image/png';
        if (!okExt || !okType) {
            if (hint) hint.textContent = 'Допустимы только JPG и PNG';
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
            img.src = reader.result;
        };
        reader.readAsDataURL(file);
    }

    input.addEventListener('change', function () {
        if (!input.files || !input.files[0]) return;
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

    if (cancelBtn) cancelBtn.addEventListener('click', closeModal);
    modal.addEventListener('click', function (e) {
        if (e.target === modal) closeModal();
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
                var dt = new DataTransfer();
                dt.items.add(new File([blob], 'photo.jpg', { type: 'image/jpeg' }));
                input.files = dt.files;
                closeModal();
                input.dispatchEvent(new Event('cropped', { bubbles: true }));
                if (hint) hint.textContent = 'Фото подготовлено для круглого аватара. Сохраните профиль.';
            }, 'image/jpeg', 0.92);
        });
    }
})();
