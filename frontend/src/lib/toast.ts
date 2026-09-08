let message = '';
let timer: ReturnType<typeof setTimeout> | undefined;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

export function showToast(text: string) {
  clearTimeout(timer);
  message = text;
  emit();
  timer = setTimeout(() => {
    message = '';
    emit();
  }, 2600);
}

export function subscribeToast(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getToastSnapshot() {
  return message;
}
