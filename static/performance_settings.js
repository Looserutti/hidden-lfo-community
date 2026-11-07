document.querySelectorAll('[data-timing-field]').forEach((slider) => {
  const field = document.getElementById(slider.dataset.timingField);
  slider.addEventListener('input', () => {
    field.value = slider.value;
  });
  field.addEventListener('input', () => {
    if (field.value !== '' && field.validity.valid) slider.value = field.value;
  });
});
