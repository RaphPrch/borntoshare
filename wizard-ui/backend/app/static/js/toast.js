export function toast(msg, type = "info") {
  const c = document.getElementById("toast-container");
  if (!c) return;
  const d = document.createElement("div");
  d.className = `toast toast-${type}`;
  d.textContent = msg;
  c.appendChild(d);
  setTimeout(() => d.remove(), 3500);
}

export const toastError = (m) => toast(m, "error");
export const toastSuccess = (m) => toast(m, "success");