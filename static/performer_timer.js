const clock = document.querySelector('#clock');
const status = document.querySelector('#status');
let state;
let receivedAt;

function draw() {
    if (!state || state.remaining === null) {
        clock.textContent = '–:––';
        clock.className = '';
        status.textContent = state ? 'Waiting for a set' : 'Timer unavailable. Reconnecting…';
        return;
    }
    const elapsed = state.paused ? 0 : (performance.now() - receivedAt) / 1000;
    const seconds = Math.max(0, Math.ceil(state.remaining - elapsed));
    clock.textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
    clock.className = seconds <= 30 ? 'red' : seconds <= 120 ? 'amber' : '';
    const label = state.paused ? 'Paused' : seconds === 0 ? 'Time’s up' : seconds <= 30 ? 'Wrap up' : 'Remaining';
    if (status.textContent !== label) status.textContent = label;
}

async function sync() {
    try {
        const response = await fetch(clock.dataset.stateUrl, {cache: 'no-store', signal: AbortSignal.timeout(3000)});
        if (!response.ok) throw new Error('Timer unavailable');
        state = await response.json();
        receivedAt = performance.now();
    } catch {
        state = null;
    }
    draw();
    setTimeout(sync, 1000);
}

setInterval(draw, 200);
sync();
