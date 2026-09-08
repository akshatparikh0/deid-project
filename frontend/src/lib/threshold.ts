// NOTE (judgment call — see README): the API contract exposes
// `Job.confidence_threshold` but has no endpoint to update it. We treat the
// value returned with the job as the threshold used at detection time, and
// let the reviewer additionally set a *display* threshold that only affects
// which low-confidence entities are emphasized/hidden client-side on the
// Rules and Review screens. It is kept in localStorage per job so it
// survives navigation between the two screens, but nothing is sent to the
// backend — there is nothing in the contract to send it to.

function key(jobId: number): string {
  return `phi-review-threshold:${jobId}`;
}

export function getDisplayThreshold(jobId: number, fallback: number): number {
  const raw = localStorage.getItem(key(jobId));
  if (raw === null) return fallback;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function setDisplayThreshold(jobId: number, value: number): void {
  localStorage.setItem(key(jobId), String(value));
}
