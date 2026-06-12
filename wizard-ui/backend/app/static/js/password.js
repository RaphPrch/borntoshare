export function computePasswordRules(password, forbidden = "") {
  const pwd = String(password || "");
  const forbid = String(forbidden || "").toLowerCase();

  return {
    length: pwd.length >= 12,
    lower: /[a-z]/.test(pwd),
    upper: /[A-Z]/.test(pwd),
    digit: /[0-9]/.test(pwd),
    special: /[^A-Za-z0-9]/.test(pwd),
    forbidden: forbid ? !pwd.toLowerCase().includes(forbid) : true
  };
}

export function applyPasswordRules(rules, prefix) {
  Object.entries(rules).forEach(([k, ok]) => {
    const el = document.getElementById(`${prefix}${k}`);
    if (!el) return;
    const label = el.textContent.replace(/^✔ |^✖ /, "");
    el.textContent = `${ok ? "✔" : "✖"} ${label}`;
    el.classList.toggle("ok", ok);
    el.classList.toggle("ko", !ok);
  });
}