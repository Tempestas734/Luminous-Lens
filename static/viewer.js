// DICOM Image Viewer functionality
document.addEventListener('DOMContentLoaded', function() {
    const img = document.getElementById('dicom-image');
    const fileId = img.dataset.fileId;
    const wwSlider = document.getElementById('ww-slider');
    const wcSlider = document.getElementById('wc-slider');
    const wwValue = document.getElementById('ww-value');
    const wcValue = document.getElementById('wc-value');
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

    function updateImage() {
        const ww = wwSlider.value;
        const wc = wcSlider.value;
        fetch(`/image_data/${fileId}?ww=${ww}&wc=${wc}`)
            .then(response => response.json())
            .then(data => {
                img.src = 'data:image/png;base64,' + data.image_data;
            })
            .catch(error => {
                console.error('Error updating image:', error);
            });
    }

    function applyTransform() {
        img.style.transformOrigin = `${originX}% ${originY}%`;
        img.style.transform = `scale(${currentZoom}) translate(${currentPanX}px, ${currentPanY}px)`;
        zoomLevel.textContent = `${Math.round(currentZoom * 100)}%`;
    }

    function updateMouseCoords(event) {
        if (!imageRect) return;
        const x = event.clientX - imageRect.left;
        const y = event.clientY - imageRect.top;
        const normX = Math.max(0, Math.min(imageRect.width, x));
        const normY = Math.max(0, Math.min(imageRect.height, y));
        mouseCoords.textContent = `X: ${Math.round(normX)}, Y: ${Math.round(normY)}`;
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

    wwSlider.addEventListener('input', function() {
        wwValue.textContent = this.value;
        updateImage();
    });

    wcSlider.addEventListener('input', function() {
        wcValue.textContent = this.value;
        updateImage();
    });

    zoomInBtn.addEventListener('click', function() {
        currentZoom = Math.min(5, currentZoom * 1.2);
        applyTransform();
    });

    zoomOutBtn.addEventListener('click', function() {
        currentZoom = Math.max(1, currentZoom / 1.2);
        applyTransform();
    });

    resetZoomBtn.addEventListener('click', function() {
        currentZoom = 1;
        currentPanX = 0;
        currentPanY = 0;
        originX = 50;
        originY = 50;
        applyTransform();
    });

    img.addEventListener('mousemove', function(event) {
        if (!imageRect) updateImageRect();
        updateMouseCoords(event);
    });

    img.addEventListener('mouseenter', updateImageRect);
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

    applyTransform();
});