document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.project-editor-form').forEach(form => {
    form.addEventListener('input', () => {
      document.querySelectorAll('.project-publish').forEach(button => button.disabled = true);
      form.querySelector('.project-save-status').textContent = 'Unsaved edits — save the draft before publishing.';
    });
    form.addEventListener('submit', event => {
      event.preventDefault();
      const button = form.querySelector('button'), status = form.querySelector('.project-save-status');
      button.disabled = true; status.textContent = 'Saving draft and preparing the photo… Any live version stays unchanged.';
      const request = new XMLHttpRequest(); request.open('POST', form.action); request.timeout = 360000;
      const fail = message => { status.textContent = message; button.disabled = false; };
      request.addEventListener('load', () => {
        if (request.status >= 200 && request.status < 300) {
          const url = new URL(request.responseURL);
          if (url.origin === location.origin && url.pathname.startsWith('/admin/projects/')) { location.assign(url.href); return; }
        }
        let message = 'The draft could not be saved. Try again.';
        try { const data = JSON.parse(request.responseText); if (typeof data.detail === 'string') message = data.detail; } catch (_) {}
        fail(message);
      });
      request.addEventListener('error', () => fail('Connection interrupted. Check saved posts before retrying.'));
      request.addEventListener('timeout', () => fail('Saving took too long. Check saved posts before retrying.'));
      request.send(new FormData(form));
    });
  });
});
