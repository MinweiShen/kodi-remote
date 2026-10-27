export function formatTime(value) {
  const t = Math.max(0, Math.floor(value || 0));
  const parts = [Math.floor(t / 60) % 60, t % 60].map(v => String(v).padStart(2, '0'));
  if (t >= 3600) parts.unshift(String(Math.floor(t / 3600)).padStart(2, '0'));
  return parts.join(':');
}

export function position(state, receivedAt, now) {
  if (!state.active) return 0;
  return Math.min(state.duration || 0, Math.max(0, (state.time || 0) + (now - receivedAt) / 1000 * (state.speed || 0)));
}

export function tapButton(gesture, now) {
  return gesture && !gesture.cancelled && !gesture.drag && now - gesture.started < 300 && gesture.distance < 9
    ? (gesture.maxFingers === 2 ? 'right' : gesture.maxFingers === 1 ? 'left' : null) : null;
}
