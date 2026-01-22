// wizard/js/api.js
export async function api(path, body = {}, timeout = 8000) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeout);

  try {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: ctrl.signal
    });

    if (!res.ok) {
      const txt = await res.text();
      try {
        const j = JSON.parse(txt);
        throw new Error(j?.detail || j?.message || txt);
      } catch {
        throw new Error(txt || `Erreur API ${res.status}`);
      }
    }

    return res.json();
  } finally {
    clearTimeout(t);
  }
}
