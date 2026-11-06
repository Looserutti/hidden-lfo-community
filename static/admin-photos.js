document.addEventListener('DOMContentLoaded', () => {
  const form = document.querySelector('.photo-upload-form');
  if (!form) return;
  const input = form.querySelector('input[type=file]');
  const zone = form.querySelector('.photo-dropzone');
  const selection = form.querySelector('.photo-selection');
  const status = form.querySelector('.photo-upload-status');
  function update() {
    selection.textContent = input.files.length ? `${input.files.length} photos selected` : 'No photos selected';
  }
  input.addEventListener('change', update);
  ['dragenter', 'dragover'].forEach(name => zone.addEventListener(name, event => {
    event.preventDefault(); zone.classList.add('is-dragging');
  }));
  ['dragleave', 'drop'].forEach(name => zone.addEventListener(name, event => {
    event.preventDefault(); zone.classList.remove('is-dragging');
  }));
  zone.addEventListener('drop', event => { input.files = event.dataTransfer.files; update(); });
  form.addEventListener('submit', event => {
    event.preventDefault();
    const button = form.querySelector('button');
    button.disabled = true;
    const request = new XMLHttpRequest();
    request.open('POST', form.action);
    request.timeout = 360000;
    function failed(message) { status.textContent = message; button.disabled = false; }
    status.textContent = 'Uploading photos… Your current carousel stays live.';
    request.upload.addEventListener('progress', event => {
      if (event.lengthComputable) status.textContent = `Uploading photos: ${Math.round(event.loaded / event.total * 100)}%`;
    });
    request.upload.addEventListener('load', () => {
      status.textContent = 'Preparing previews… Keep this page open. Your current carousel stays live.';
    });
    request.addEventListener('load', () => {
      if (request.status >= 200 && request.status < 300) {
        const destination = new URL(request.responseURL);
        if (destination.origin === location.origin && destination.pathname.startsWith('/admin/photos/')) {
          location.assign(destination.href); return;
        }
      }
      let message = 'The batch could not be uploaded. Try a smaller batch or check your connection.';
      try { const body = JSON.parse(request.responseText); if (typeof body.detail === 'string') message = body.detail; } catch (_) {}
      failed(message);
    });
    request.addEventListener('error', () => failed('Upload interrupted. Check your connection and try again.'));
    request.addEventListener('timeout', () => failed('Upload took too long. Try a smaller batch; check Saved batches before retrying.'));
    request.send(new FormData(form));
  });
});
