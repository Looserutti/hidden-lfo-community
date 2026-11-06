/* User-initiated gallery music. Photo navigation never restarts the track. */
document.addEventListener('DOMContentLoaded', () => {
  const viewer = document.querySelector('.photo-viewer');
  const data = document.querySelector('#gallery-playlist');
  if (!viewer || !data) return;
  const tracks = JSON.parse(data.textContent);
  if (!tracks.length) return;
  const audio = viewer.querySelector('.player-audio');
  const choices = [...viewer.querySelectorAll('.player-track-choice')];
  const status = viewer.querySelector('.player-status');
  let index = 0;
  let initialized = false;
  function choose(next, resume = false) {
    audio.pause();
    index = (next + tracks.length) % tracks.length;
    audio.src = tracks[index].url;
    viewer.querySelector('.player-title').textContent = tracks[index].title;
    viewer.querySelector('.player-artist').textContent = tracks[index].artist;
    choices.forEach((button,i) => button.setAttribute('aria-current', String(i === index)));
    audio.setAttribute('aria-label', `Gallery music: ${tracks[index].title}`);
    status.textContent = '';
    initialized = true;
    if (resume && viewer.open) audio.play().catch(() => { status.textContent = 'Press Play to start the track.'; });
  }
  viewer.addEventListener('gallery:open', () => { if (!initialized) choose(0); });
  viewer.addEventListener('close', () => { audio.pause(); viewer.querySelector('.player-details').open = false; });
  audio.addEventListener('play', () => { if (!viewer.open) audio.pause(); });
  audio.addEventListener('error', () => { status.textContent = 'This track could not be loaded. Try another track.'; });
  audio.addEventListener('ended', () => { if (tracks.length > 1 && viewer.open) choose(index + 1, true); });
  choices.forEach(button => button.addEventListener('click', () => choose(Number(button.dataset.trackIndex), !audio.paused)));
  viewer.querySelector('.player-previous').addEventListener('click', () => choose(index - 1, !audio.paused));
  viewer.querySelector('.player-next').addEventListener('click', () => choose(index + 1, !audio.paused));
  for (const button of viewer.querySelectorAll('.player-previous, .player-next')) button.disabled = tracks.length < 2;
});
