document.addEventListener('DOMContentLoaded', function() {
    const importFormGlobal = document.getElementById('import-form-global');
    const importInputGlobal = document.getElementById('import-dicom-global');
    const importBtnGlobal = document.getElementById('import-btn-global');

    if (importFormGlobal && importInputGlobal && importBtnGlobal) {
        importBtnGlobal.addEventListener('click', () => importInputGlobal.click());

        importInputGlobal.addEventListener('change', () => {
            if (importInputGlobal.files.length > 0) {
                importFormGlobal.submit();
            }
        });
    }

    // Upload page behaviors
    const uploadZone = document.getElementById('upload-zone');
    const fileInput = document.getElementById('dicom_file');
    const browseBtn = document.getElementById('browse-btn');
    const uploadForm = document.getElementById('upload-form');

    if (uploadZone && fileInput && browseBtn && uploadForm) {
        browseBtn.addEventListener('click', () => fileInput.click());

        fileInput.addEventListener('change', () => {
            if (fileInput.files.length > 0) {
                uploadForm.submit();
            }
        });

        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }

        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            uploadZone.addEventListener(eventName, preventDefaults, false);
        });

        function highlight() {
            uploadZone.classList.add('drag-over');
        }

        function unhighlight() {
            uploadZone.classList.remove('drag-over');
        }

        ['dragenter', 'dragover'].forEach(eventName => {
            uploadZone.addEventListener(eventName, highlight, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            uploadZone.addEventListener(eventName, unhighlight, false);
        });

        uploadZone.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files.length > 0) {
                fileInput.files = files;
                uploadForm.submit();
            }
        });
    }

    // Tag search behavior
    const tagSearch = document.getElementById('tag-search');
    if (tagSearch) {
        tagSearch.addEventListener('input', function() {
            const query = this.value.toLowerCase();
            const rows = document.querySelectorAll('.tag-row');
            rows.forEach(row => {
                const tag = row.dataset.tag.toLowerCase();
                const name = row.dataset.name.toLowerCase();
                row.style.display = tag.includes(query) || name.includes(query) ? '' : 'none';
            });
        });
    }

    // Viewer behavior
    const img = document.getElementById('dicom-image');
    if (img) {
        const fileId = img.dataset.fileId;
        const sliceSlider = document.getElementById('slice-slider');
        const sliceIndicator = document.getElementById('slice-indicator');
        const playSlicesBtn = document.getElementById('play-slices');
        const pauseSlicesBtn = document.getElementById('pause-slices');
        const speedButtons = Array.from(document.querySelectorAll('.slice-speed-btn'));
        const wwSlider = document.getElementById('ww-slider');
        const wcSlider = document.getElementById('wc-slider');
        const wwValue = document.getElementById('ww-value');
        const wcValue = document.getElementById('wc-value');
        const wwMinLabel = document.getElementById('ww-min-label');
        const wwMaxLabel = document.getElementById('ww-max-label');
        const wcMinLabel = document.getElementById('wc-min-label');
        const wcMaxLabel = document.getElementById('wc-max-label');
        const zoomInBtn = document.getElementById('zoom-in');
        const zoomOutBtn = document.getElementById('zoom-out');
        const resetZoomBtn = document.getElementById('reset-zoom');
        const mouseCoords = document.getElementById('mouse-coords');
        const zoomLevel = document.getElementById('zoom-level');

        let currentZoom = 1;
        let currentPanX = 0;
        let currentPanY = 0;
        let originX = 50;
        let originY = 50;
        let imageRect = null;
        let isPanning = false;
        let startPanX = 0;
        let startPanY = 0;
        let startMouseX = 0;
        let startMouseY = 0;
        let currentFrame = Number(img.dataset.currentFrame || 0);
        const sliceCount = Number(img.dataset.sliceCount || 1);
        let autoplayId = null;
        let autoplayDelay = 1000;
        let isAutoplaying = false;

        function updateWindowControls(data) {
            if (typeof data.window_width === 'number') {
                wwSlider.value = String(data.window_width);
                if (wwValue) wwValue.textContent = String(data.window_width);
            }
            if (typeof data.window_center === 'number') {
                wcSlider.value = String(data.window_center);
                if (wcValue) wcValue.textContent = String(data.window_center);
            }
            if (data.window_bounds) {
                wwSlider.min = String(data.window_bounds.ww_min);
                wwSlider.max = String(data.window_bounds.ww_max);
                wcSlider.min = String(data.window_bounds.wc_min);
                wcSlider.max = String(data.window_bounds.wc_max);
                if (wwMinLabel) wwMinLabel.textContent = Number(data.window_bounds.ww_min).toFixed(2);
                if (wwMaxLabel) wwMaxLabel.textContent = Number(data.window_bounds.ww_max).toFixed(2);
                if (wcMinLabel) wcMinLabel.textContent = Number(data.window_bounds.wc_min).toFixed(2);
                if (wcMaxLabel) wcMaxLabel.textContent = Number(data.window_bounds.wc_max).toFixed(2);
            }
        }

        function updateImage(useFrameDefaults = false) {
            if (!fileId) return;
            const ww = wwSlider.value;
            const wc = wcSlider.value;
            const params = new URLSearchParams({
                ww,
                wc,
                frame: String(currentFrame),
            });
            if (useFrameDefaults) {
                params.set('use_frame_defaults', '1');
            }
            fetch(`/image_data/${fileId}?${params.toString()}`)
                .then(response => response.json())
                .then(data => {
                    img.src = 'data:image/png;base64,' + data.image_data;
                    if (typeof data.frame_index === 'number') {
                        currentFrame = data.frame_index;
                        img.dataset.currentFrame = String(currentFrame);
                    }
                    updateWindowControls(data);
                    updateSliceUI();
                })
                .catch(error => {
                    console.error('Error updating image:', error);
                });
        }

        function updateSliceUI() {
            if (sliceIndicator) {
                sliceIndicator.textContent = `COUPE: ${currentFrame + 1}/${sliceCount}`;
            }
            if (sliceSlider) {
                sliceSlider.value = String(currentFrame + 1);
            }
        }

        function setPlaybackButtonState() {
            if (playSlicesBtn) {
                playSlicesBtn.className = `inline-flex h-9 w-9 items-center justify-center rounded-sm transition-colors ${
                    isAutoplaying
                        ? 'bg-primary text-on-primary hover:bg-primary-dim'
                        : 'bg-surface-container-high text-on-surface hover:bg-primary hover:text-on-primary'
                }`;
            }
            if (pauseSlicesBtn) {
                pauseSlicesBtn.className = `inline-flex h-9 w-9 items-center justify-center rounded-sm transition-colors ${
                    isAutoplaying
                        ? 'bg-surface-container-high text-on-surface hover:bg-surface-container-highest'
                        : 'bg-primary text-on-primary hover:bg-primary-dim'
                }`;
            }
        }

        function setSpeedState(speedValue) {
            speedButtons.forEach((button) => {
                const active = Number(button.dataset.speed) === speedValue;
                button.className = active
                    ? 'slice-speed-btn rounded-sm px-2 py-1 text-[10px] font-semibold bg-primary text-on-primary transition-colors'
                    : 'slice-speed-btn rounded-sm px-2 py-1 text-[10px] font-semibold text-on-surface-variant hover:bg-surface-container-highest hover:text-on-surface transition-colors';
            });
        }

        function stopAutoplay() {
            if (autoplayId) {
                window.clearInterval(autoplayId);
                autoplayId = null;
            }
            isAutoplaying = false;
            setPlaybackButtonState();
        }

        function startAutoplay() {
            if (!sliceSlider || sliceCount <= 1 || autoplayId) return;
            isAutoplaying = true;
            setPlaybackButtonState();
            autoplayId = window.setInterval(() => {
                currentFrame = (currentFrame + 1) % sliceCount;
                updateSliceUI();
                updateImage(true);
            }, autoplayDelay);
        }

        function applyTransform() {
            img.style.transformOrigin = `${originX}% ${originY}%`;
            img.style.transform = `scale(${currentZoom}) translate(${currentPanX}px, ${currentPanY}px)`;
            if (zoomLevel) {
                zoomLevel.textContent = `${Math.round(currentZoom * 100)}%`;
            }
        }

        function updateMouseCoords(event) {
            if (!imageRect) return;
            const x = event.clientX - imageRect.left;
            const y = event.clientY - imageRect.top;
            const normX = Math.max(0, Math.min(imageRect.width, x));
            const normY = Math.max(0, Math.min(imageRect.height, y));
            if (mouseCoords) {
                mouseCoords.textContent = `X: ${Math.round(normX)}, Y: ${Math.round(normY)}`;
            }
        }

        function setZoomOrigin(event) {
            if (!imageRect) return;
            const x = event.clientX - imageRect.left;
            const y = event.clientY - imageRect.top;
            originX = Math.round((x / imageRect.width) * 100);
            originY = Math.round((y / imageRect.height) * 100);
        }

        function updateImageRect() {
            imageRect = img.getBoundingClientRect();
        }

        if (wwSlider) {
            wwSlider.addEventListener('input', function() {
                if (wwValue) wwValue.textContent = this.value;
                updateImage(false);
            });
        }

        if (wcSlider) {
            wcSlider.addEventListener('input', function() {
                if (wcValue) wcValue.textContent = this.value;
                updateImage(false);
            });
        }

        if (sliceSlider) {
            sliceSlider.addEventListener('input', function() {
                stopAutoplay();
                currentFrame = Math.max(0, Number(this.value) - 1);
                updateSliceUI();
                updateImage(true);
            });
        }

        if (playSlicesBtn) {
            playSlicesBtn.addEventListener('click', function() {
                startAutoplay();
            });
        }

        if (pauseSlicesBtn) {
            pauseSlicesBtn.addEventListener('click', function() {
                stopAutoplay();
            });
        }

        speedButtons.forEach((button) => {
            button.addEventListener('click', function() {
                const speed = Number(this.dataset.speed || 1);
                if (speed === 0.5) autoplayDelay = 2000;
                if (speed === 1) autoplayDelay = 1000;
                if (speed === 2) autoplayDelay = 500;
                if (speed === 3) autoplayDelay = 333;
                setSpeedState(speed);
                if (isAutoplaying) {
                    stopAutoplay();
                    startAutoplay();
                }
            });
        });

        if (zoomInBtn) {
            zoomInBtn.addEventListener('click', function() {
                currentZoom = Math.min(5, currentZoom * 1.2);
                applyTransform();
            });
        }

        if (zoomOutBtn) {
            zoomOutBtn.addEventListener('click', function() {
                currentZoom = Math.max(1, currentZoom / 1.2);
                applyTransform();
            });
        }

        if (resetZoomBtn) {
            resetZoomBtn.addEventListener('click', function() {
                currentZoom = 1;
                currentPanX = 0;
                currentPanY = 0;
                originX = 50;
                originY = 50;
                applyTransform();
            });
        }

        img.addEventListener('mousemove', function(event) {
            if (!imageRect) updateImageRect();
            updateMouseCoords(event);
        });

        img.addEventListener('mouseenter', updateImageRect);
        img.addEventListener('load', updateImageRect);
        window.addEventListener('resize', updateImageRect);

        img.addEventListener('wheel', function(e) {
            e.preventDefault();
            if (!imageRect) updateImageRect();
            setZoomOrigin(e);
            const delta = e.deltaY < 0 ? 1.1 : 0.9;
            currentZoom = Math.max(1, Math.min(5, currentZoom * delta));
            applyTransform();
        });

        img.addEventListener('mousedown', function(e) {
            isPanning = true;
            startPanX = currentPanX;
            startPanY = currentPanY;
            startMouseX = e.clientX;
            startMouseY = e.clientY;
            img.style.cursor = 'grabbing';
        });

        document.addEventListener('mousemove', function(e) {
            if (!isPanning) return;
            currentPanX = startPanX + (e.clientX - startMouseX);
            currentPanY = startPanY + (e.clientY - startMouseY);
            applyTransform();
        });

        document.addEventListener('mouseup', function() {
            if (isPanning) {
                isPanning = false;
                img.style.cursor = 'grab';
            }
        });

        updateSliceUI();
        setPlaybackButtonState();
        setSpeedState(1);
        applyTransform();
    }
});
