// wizard/js/logger.js
// Minimal in-browser install log.
// - Writes to console
// - Keeps last N lines in memory (and localStorage)
// - Optional server append if /api/log exists (non-blocking)

const MAX_LINES = 800;
const KEY = "b2s_wizard_install_log_v1";

let lines = [];

function now() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function pushLine(level, msg, meta) {
  const base = `[${now()}] [${level}] ${msg}`;
  const line = meta ? `${base} ${safeJson(meta)}` : base;

  lines.push(line);
  if (lines.length > MAX_LINES) lines = lines.slice(lines.length - MAX_LINES);

  try { localStorage.setItem(KEY, JSON.stringify(lines)); } catch {}

  return line;
}

function safeJson(x) {
  try { return JSON.stringify(x); } catch { return ""; }
}

async function tryServerAppend(line) {
  // Optional: backend may expose /api/runtime/log
  try {
    await fetch("/api/runtime/log", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ level: "info", message: line })
    });
  } catch {
    // ignore
  }
}

export function logInfo(msg, meta) {
  const line = pushLine("INFO", msg, meta);
  console.info("[WIZARD]", msg, meta || "");
  // fire and forget
  tryServerAppend(line);
}

export function logWarn(msg, meta) {
  const line = pushLine("WARN", msg, meta);
  console.warn("[WIZARD]", msg, meta || "");
  tryServerAppend(line);
}

export function logError(msg, meta) {
  const line = pushLine("ERROR", msg, meta);
  console.error("[WIZARD]", msg, meta || "");
  tryServerAppend(line);
}

export function getInstallLog() {
  if (lines.length) return lines.join("\n");
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return "";
    const arr = JSON.parse(raw);
    if (Array.isArray(arr)) return arr.join("\n");
  } catch {}
  return "";
}

export function clearInstallLog() {
  lines = [];
  try { localStorage.removeItem(KEY); } catch {}
}
