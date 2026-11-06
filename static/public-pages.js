document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.site-menu').forEach(menu => {
    document.addEventListener('pointerdown', event => { if (!menu.contains(event.target)) menu.open = false; });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && menu.open && !document.querySelector('dialog[open]')) {
        menu.open = false; menu.querySelector('summary').focus(); event.preventDefault();
      }
    });
  });
  document.querySelectorAll('.project-photo-toggle').forEach(button => {
    button.addEventListener('click', () => {
      const color = button.getAttribute('aria-pressed') !== 'true';
      button.setAttribute('aria-pressed', String(color));
      button.classList.toggle('is-color', color);
      button.setAttribute('aria-label', `${button.dataset.label} — show in ${color ? 'monochrome' : 'color'}`);
    });
  });
});
