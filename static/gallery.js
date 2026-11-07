
document.addEventListener("DOMContentLoaded", () => {
  const gallery = document.querySelector(".home-gallery");
  if (!gallery) return;

  const images = [...gallery.querySelectorAll(".gallery-image")];
  if (!images.length) return;

  const viewer = document.querySelector(".photo-viewer");
  const viewerImage = viewer.querySelector(".viewer-image");
  const expand = gallery.querySelector(".gallery-expand");
  let returnFocus;
  let previousOverflow;
  let current = 0;
  let timer;
  let pendingPhoto = 0;
  const loading = viewer.querySelector('.viewer-loading');

  function loadViewerPhoto() {
    const ticket = ++pendingPhoto;
    const image = images[current];
    const source = image.dataset.fullSrc || image.currentSrc || image.src;
    if (viewerImage.getAttribute('src') === source) {
      loading.textContent = '';
      return;
    }
    loading.textContent = 'Loading photo…';
    const ready = new Image();
    ready.src = source;
    ready.decode().then(() => {
      if (ticket !== pendingPhoto) return;
      viewerImage.src = source;
      viewerImage.alt = image.alt;
      loading.textContent = '';
    }).catch(() => {
      if (ticket === pendingPhoto) loading.textContent = 'Couldn’t load that photo. Try another.';
    });
  }

  function hydrate(image) {
    if (!image.dataset.src) return;
    if (image.dataset.srcset) image.srcset = image.dataset.srcset;
    image.src = image.dataset.src;
    delete image.dataset.src;
    delete image.dataset.srcset;
  }

  function warmNext() {
    if (navigator.connection?.saveData) return;
    hydrate(images[(current + 1) % images.length]);
  }

  function showPhoto(index) {
    current = (index + images.length) % images.length;

    hydrate(images[current]);
    images.forEach((image, i) => {
      image.classList.toggle("is-active", i === current);
      image.classList.remove("is-color");
    });

    if (images[current].complete && images[current].naturalWidth) warmNext();
    if (viewer.open) loadViewerPhoto();
    viewer.querySelector(".viewer-current").textContent = String(current + 1).padStart(2, "0");
  }

  function stopTimer() {
    clearInterval(timer);
  }

  function startTimer() {
    stopTimer();

    if (viewer.open || images[current].classList.contains("is-color")) return;

    timer = setInterval(() => {
      if (!images[current].classList.contains("is-color")) {
        showPhoto(current + 1);
      }
    }, 6000);
  }

  images.forEach((image) => {
    image.addEventListener("click", () => {
      if (!image.classList.contains("is-active")) return;

      image.classList.toggle("is-color");

      if (image.classList.contains("is-color")) {
        stopTimer();
      } else {
        startTimer();
      }
    });
  });

  function openViewer() {
    if (viewer.open) return;
    returnFocus = document.activeElement;
    previousOverflow = document.body.style.overflow;
    stopTimer();
    viewer.showModal();
    loadViewerPhoto();
    viewer.dispatchEvent(new Event("gallery:open"));
    document.body.style.overflow = "hidden";
  }

  expand.addEventListener("click", openViewer);
  images.forEach((image) => {
    image.addEventListener("dblclick", () => {
      if (image.classList.contains("is-active")) openViewer();
    });
  });
  viewer.querySelector(".viewer-close").addEventListener("click", () => viewer.close());
  viewer.querySelector(".gallery-prev").addEventListener("click", () => showPhoto(current - 1));
  viewer.querySelector(".gallery-next").addEventListener("click", () => showPhoto(current + 1));
  viewer.addEventListener("keydown", (event) => {
    if (event.target.closest("audio, input, select, .gallery-player")) return;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      showPhoto(current + (event.key === "ArrowLeft" ? -1 : 1));
    }
  });
  viewer.addEventListener("close", () => {
    document.body.style.overflow = previousOverflow;
    returnFocus?.focus();
    startTimer();
  });

  showPhoto(0);
  // Warm only the adjacent slide, after the visible image has finished loading.
  images.forEach(image => image.addEventListener('load', () => {
    if (image === images[current]) warmNext();
  }));
  if (images[0].complete && images[0].naturalWidth) warmNext();
  startTimer();
});
