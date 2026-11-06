// Dates in HTML carry timezone-aware ISO 8601 timestamps from the backend.
document.querySelectorAll('time.local-time[datetime]').forEach((element) => {
  const date = new Date(element.dateTime);
  if (Number.isNaN(date.getTime())) return;
  element.textContent = new Intl.DateTimeFormat(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit', timeZoneName: 'short'
  }).format(date);
  element.title = 'Displayed in your device’s local time zone';
});
