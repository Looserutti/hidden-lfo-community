
document.addEventListener("DOMContentLoaded", () => {
  const gallery = document.querySelector(".home-gallery");
  if (!gallery) return;

  const images = [...gallery.querySelectorAll(".gallery-image")];
  const previous = gallery.querySelector(".gallery-prev");
  const next = gallery.querySelector(".gallery-next");
  const counter = gallery.querySelector("#gallery-current");

  if (!images.length || !previous || !next || !counter) return;

  let current = 0;
  let timer;

  function showPhoto(index) {
    current = (index + images.length) % images.length;

    images.forEach((image, i) => {
      image.classList.toggle("is-active", i === current);
      image.classList.remove("is-color");
    });

    counter.textContent = String(current + 1).padStart(2, "0");
  }

  function stopTimer() {
    clearInterval(timer);
  }

  function startTimer() {
    stopTimer();

    timer = setInterval(() => {
      if (!images[current].classList.contains("is-color")) {
        showPhoto(current + 1);
      }
    }, 6000);
  }

  previous.addEventListener("click", () => {
    showPhoto(current - 1);
    startTimer();
  });

  next.addEventListener("click", () => {
    showPhoto(current + 1);
    startTimer();
  });

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

  showPhoto(0);
  startTimer();
});
