/* Progressive loading; ordinary links remain usable without JavaScript. */
(() => {
  const agenda = document.querySelector('.calendar-agenda');
  if (!agenda) return;
  const today = agenda.querySelector('.agenda-today-link');
  today?.addEventListener('click', (event) => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const target = new URL(today.href);
    if (target.pathname === location.pathname && target.search === location.search) {
      event.preventDefault();
      location.hash = target.hash;
      location.reload();
    }
  });
  const more = agenda.querySelector('.agenda-load-more');
  if (!more) return;
  const status = agenda.querySelector('.agenda-status');
  let loading = false;
  more.addEventListener('click', async (event) => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (loading) return;
    loading = true;
    more.setAttribute('aria-disabled', 'true');
    status.textContent = 'Loading more events…';
    try {
      const response = await fetch(more.href, { credentials: 'same-origin' });
      if (!response.ok) throw new Error('Calendar request failed');
      const page = new DOMParser().parseFromString(await response.text(), 'text/html');
      const next = page.querySelector('.calendar-agenda');
      if (!next) throw new Error('Calendar response missing');
      const days = [...next.querySelectorAll('.agenda-day')];
      const firstNewEvent = days[0]?.querySelector('.agenda-event');
      for (const day of days) {
        const existing = agenda.querySelector(`#${day.getAttribute('aria-labelledby')}`)?.closest('.agenda-day');
        if (existing) existing.querySelector('.agenda-events').append(...day.querySelector('.agenda-events').children);
        else agenda.querySelector('.agenda-list').append(day);
      }
      const count = agenda.querySelector('.agenda-count');
      const last = next.querySelector('.agenda-count').dataset.last;
      count.dataset.last = last;
      count.textContent = `Events ${count.dataset.first}–${last} · starting today`;
      const range = agenda.querySelector('.agenda-range');
      const newRange = next.querySelector('.agenda-range').textContent;
      range.textContent = `${range.textContent.split(' – ')[0]} – ${newRange.split(' – ')[1]}`;
      const nextArrow = agenda.querySelector('.agenda-next');
      const newArrow = next.querySelector('.agenda-next');
      if (nextArrow && newArrow) nextArrow.href = newArrow.href;
      else if (nextArrow) { const disabled = document.createElement('span'); disabled.setAttribute('aria-disabled','true'); disabled.textContent='Next →'; nextArrow.replaceWith(disabled); }
      const following = next.querySelector('.agenda-load-more');
      if (following) more.href = following.href;
      else more.remove();
      status.textContent = days.length ? 'More events loaded.' : 'No more events published.';
      if (firstNewEvent) { firstNewEvent.focus({ preventScroll: true }); firstNewEvent.scrollIntoView({ block: 'start', behavior: 'auto' }); }
    } catch (_) {
      status.textContent = 'Could not load more events. Please try again.';
    } finally {
      loading = false;
      more.removeAttribute('aria-disabled');
    }
  });
})();
