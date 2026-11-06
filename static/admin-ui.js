document.addEventListener('DOMContentLoaded', () => {
  // Preserve old event-management bookmarks after the control-hub split.
  if (location.pathname === '/admin' && ['#create-event', '#member-submissions'].includes(location.hash)) {
    location.replace('/admin/calendar' + location.hash); return;
  }
  const menu = document.querySelector('.admin-mobile-navigation');
  if (!menu) return;
  document.addEventListener('pointerdown', event => { if (!menu.contains(event.target)) menu.open = false; });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && menu.open) { menu.open = false; menu.querySelector('summary').focus(); }
  });
});
