/* -----------------------------------------------------
 BornToShare Wizard v5 — JS contrôleur principal
 GitHub publishable — PROD READY
----------------------------------------------------- */

"use strict";

/* =====================================================
   CONSTANTES & STEPS
===================================================== */
const STORAGE_KEY = "b2s_wizard_state_v5";

/**
 * Steps réellement présents dans l'HTML
 */
const STEPS = [1, 2, 3, 4, 7, 8];
const FIRST_STEP = STEPS[0];
const LAST_STEP = STEPS[STEPS.length - 1];

let currentStep = FIRST_STEP;

/* =====================================================
   ÉTAT GLOBAL
===================================================== */
const state = {
  admin: {},
  db_root: {},
  db_name: "",
  app_user_name: "",
  app_user_password: "",
  services: []
};

/**
 * Validation minimale par step
 */
const stepStatus = {
  1: true,
  2: false,
  3: false,
  4: false
};

/* =====================================================
   HELPERS DOM
===================================================== */
const id = (x) => document.getElementById(x);
const value = (x) => id(x)?.value ?? "";
const setValue = (x, v) => {
  const el = id(x);
  if (el) el.value = v ?? "";
};

/* =====================================================
   UX HELPERS (STEPPER / WARNINGS / PRIVS)
===================================================== */
function setStepperDbStatus(status) {
  const el = id("stepper-db");
  if (!el) return;

  el.classList.remove("step-ok", "step-warning");

  if (status === "ok") el.classList.add("step-ok");
  else if (status === "warning") el.classList.add("step-warning");
}

function showNonRootWarning(show) {
  const el = id("db_non_root_warning");
  if (!el) return;
  el.style.display = show ? "block" : "none";
}

/**
 * Met à jour visuellement la ligne privilège (li id="priv_*")
 * - Ajoute classes ok/ko pour que ton CSS puisse colorer
 */
function updatePriv(idEl, ok) {
  const el = id(idEl);
  if (!el) return;

  el.classList.remove("ok", "ko");
  el.classList.add(ok ? "ok" : "ko");

  // Si tu veux un texte dynamique:
  // (ne casse pas si tu préfères garder le texte fixe)
  const base = el.textContent.split(":")[0].trim();
  el.textContent = `${base}: ${ok ? "OK" : "MANQUANT"}`;
}

/* =====================================================
   PERSISTENCE
===================================================== */
function persistState() {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ currentStep, state, stepStatus })
    );
  } catch {}
}

function restoreState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;

    const parsed = JSON.parse(raw);
    if (parsed?.state) Object.assign(state, parsed.state);
    if (parsed?.stepStatus) Object.assign(stepStatus, parsed.stepStatus);

    const restoredStep = Number(parsed.currentStep);
    if (STEPS.includes(restoredStep)) currentStep = restoredStep;
  } catch {}
}

/* =====================================================
   PASSWORD RULES
===================================================== */
function computePasswordRules(password, forbidden = "") {
  const pwd = String(password || "");
  const forbid = String(forbidden || "");

  return {
    length: pwd.length >= 12,
    lower: /[a-z]/.test(pwd),
    upper: /[A-Z]/.test(pwd),
    digit: /[0-9]/.test(pwd),
    special: /[^A-Za-z0-9]/.test(pwd),
    forbidden: forbid ? !pwd.includes(forbid) : true
  };
}

function applyPasswordRules({ rules, rulePrefix }) {
  Object.entries(rules).forEach(([key, ok]) => {
    const el = id(`${rulePrefix}${key}`);
    if (!el) return;

    const label = el.textContent.replace(/^✔ |^✖ /, "");
    el.textContent = (ok ? "✔ " : "✖ ") + label;

    el.classList.toggle("ok", ok);
    el.classList.toggle("ko", !ok);
  });
}

/* =====================================================
   STEP 2 — ADMIN
===================================================== */
function validateAdminForm() {
  const pwd = value("admin_password");
  const user = value("admin_username");

  const rules = computePasswordRules(pwd, user);
  applyPasswordRules({ rules, rulePrefix: "rule-" });

  const ok = Object.values(rules).every(Boolean);

  const btn = id("admin_next_btn");
  if (btn) btn.disabled = !ok;

  if (ok) {
    state.admin = {
      username: user,
      email: value("admin_email"),
      password: pwd
    };
    stepStatus[2] = true;
  } else {
    stepStatus[2] = false;
  }

  updateStepperAll();
  persistState();
  return ok;
}

/* =====================================================
   STEP 4 — APP USER
===================================================== */
function validateAppUserForm() {
  const pwd = value("app_user_password");
  const dbName = value("db_name");
  const appUserName = value("app_user_name");

  const rules = computePasswordRules(pwd);
  applyPasswordRules({ rules, rulePrefix: "app-rule-" });

  const ok = Object.values(rules).every(Boolean) && !!String(dbName || "").trim();

  const btn = id("app_next_btn");
  if (btn) btn.disabled = !ok;

  if (ok) {
    state.db_name = String(dbName || "").trim();
    state.app_user_name = (appUserName || "b2s_app").trim();
    state.app_user_password = pwd;
    stepStatus[4] = true;
  } else {
    stepStatus[4] = false;
  }

  updateStepperAll();
  persistState();
  return ok;
}

/* =====================================================
   STEPPER / PROGRESS
===================================================== */
function updateProgress() {
  const idx = STEPS.indexOf(currentStep);
  const pct = Math.round((idx / (STEPS.length - 1)) * 100);

  const bar = id("b2s_progress_bar");
  if (bar) bar.style.width = pct + "%";

  const label = id("b2s_progress_label");
  if (label) label.textContent = `Étape ${idx + 1} sur ${STEPS.length}`;
}

function showStep(step) {
  const target = Number(step);
  if (!STEPS.includes(target)) return;

  currentStep = target;

  document.querySelectorAll(".b2s-step").forEach((s) => {
    s.classList.toggle("active", Number(s.dataset.step) === currentStep);
  });

  document.querySelectorAll(".b2s-stepper li").forEach((li) => {
    li.classList.toggle("active", Number(li.dataset.step) === currentStep);
  });

  if (currentStep === 7) renderSummaryUI();

  updateProgress();
  updateStepperAll();
  persistState();
}

/**
 * Empêche de cliquer un step non autorisé.
 */
function updateStepperAll() {
  document.querySelectorAll(".b2s-stepper li").forEach((li) => {
    const step = Number(li.dataset.step);
    const idx = STEPS.indexOf(step);
    if (idx === -1) {
      li.style.opacity = "0.3";
      li.style.cursor = "not-allowed";
      li.onclick = null;
      return;
    }

    const allowed =
      step === FIRST_STEP ||
      STEPS.indexOf(step) <= STEPS.indexOf(currentStep) ||
      !!stepStatus[step];

    li.style.opacity = allowed ? "1" : "0.45";
    li.style.cursor = allowed ? "pointer" : "not-allowed";
    li.onclick = allowed ? () => showStep(step) : null;
  });
}

/* =====================================================
   NAVIGATION
===================================================== */
function validateStep(step) {
  if (step === 1) return true;
  if (step === 2) return validateAdminForm();
  if (step === 3) {
    if (!stepStatus[3]) {
      toastError("Connexion DB non validée.");
      return false;
    }
    return true;
  }
  if (step === 4) return validateAppUserForm();
  return true;
}

/**
 * ⬅️ C’EST CETTE FONCTION QUI MANQUAIT CHEZ TOI
 * Et ton HTML appelle onclick="nextStep()"
 */
function nextStep() {
  if (!validateStep(currentStep)) return;

  const idx = STEPS.indexOf(currentStep);
  const next = STEPS[Math.min(idx + 1, STEPS.length - 1)];
  showStep(next);
}

/* =====================================================
   DIAGNOSTIC RÉSEAU (DNS / TCP / LATENCE)
===================================================== */
function setDiag(elId, text, status) {
  const el = id(elId);
  if (!el) return;

  // Ton HTML diag rows ont class="b2s-diagnostic-row diag-*"
  el.classList.remove("diag-ok", "diag-ko", "diag-pending");
  el.classList.add(`diag-${status}`);

  // Ton HTML contient un <span class="b2s-diagnostic-label">...</span>
  const label = el.querySelector?.(".b2s-diagnostic-label");
  if (label) label.textContent = text;
  else el.textContent = text; // fallback
}

async function runNetworkDiagnostic() {
  const host = value("db_host");
  const port = Number(value("db_port"));

  setDiag("diag_dns", "DNS : en cours…", "pending");
  setDiag("diag_tcp", "TCP : en cours…", "pending");
  setDiag("diag_latency", "Latence : —", "pending");

  try {
    const res = await api("/api/db/diagnostic", { host, port }, 5000);

    setDiag("diag_dns", res.dns_ok ? "DNS : OK" : "DNS : échec", res.dns_ok ? "ok" : "ko");
    setDiag("diag_tcp", res.tcp_ok ? "TCP : OK" : "TCP : port inaccessible", res.tcp_ok ? "ok" : "ko");

    if (res.latency_ms !== null && res.latency_ms !== undefined) {
      setDiag(
        "diag_latency",
        `Latence : ${res.latency_ms} ms`,
        res.latency_ms < 100 ? "ok" : "pending"
      );
    } else {
      setDiag("diag_latency", "Latence : —", "pending");
    }

    return !!res.dns_ok && !!res.tcp_ok;
  } catch {
    setDiag("diag_dns", "DNS : erreur", "ko");
    setDiag("diag_tcp", "TCP : erreur", "ko");
    setDiag("diag_latency", "Latence : —", "ko");
    return false;
  }
}

/* =====================================================
   STEP 3 — TEST DB COMPLET
===================================================== */
async function testDb(ev) {
  const btn = ev?.target;
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Diagnostics en cours…";
  }

  const cfg = {
    host: value("db_host"),
    port: Number(value("db_port")),
    user: value("db_user"),
    password: value("db_password")
  };

  try {
    // 1) DNS/TCP
    const netOk = await runNetworkDiagnostic();
    if (!netOk) throw new Error("Problème réseau détecté (DNS ou TCP).");

    // 2) MySQL + droits
    const res = await api("/api/db/test", cfg);

    if (!res || !res.privileges) {
      throw new Error("Impossible de vérifier les droits SQL.");
    }

    const priv = res.privileges;

    // 3) UI privilèges
    updatePriv("priv_create_db", !!priv.create_db);
    updatePriv("priv_create_user", !!priv.create_user);
    updatePriv("priv_grant", !!priv.grant);
    updatePriv("priv_create_table", !!priv.create_table);

    // 4) Règle minimale: CREATE TABLE requis
    if (!priv.create_table) {
      throw new Error("Le compte SQL ne permet pas de créer des tables.");
    }

    const isRoot = res.is_root === true;
    const fullRights = !!priv.create_db && !!priv.create_user && !!priv.grant;

    // 5) Wizard state
    state.db_root = cfg;
    stepStatus[3] = true;

    const nextBtn = id("db_next_btn");
    if (nextBtn) nextBtn.disabled = false;

    // 6) UX
    if (isRoot || fullRights) {
      setStepperDbStatus("ok");
      showNonRootWarning(false);
      toastSuccess("DB validée (droits complets).");
    } else {
      setStepperDbStatus("warning");
      showNonRootWarning(true);
      toastSuccess("DB utilisable (non-root, droits suffisants).");
    }
  } catch (e) {
    stepStatus[3] = false;

    const nextBtn = id("db_next_btn");
    if (nextBtn) nextBtn.disabled = true;

    setStepperDbStatus(null);
    showNonRootWarning(false);

    toastError(e?.message || "Connexion à la base impossible.");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Tester la connexion";
    }
    updateStepperAll();
    persistState();
  }
}

/* =====================================================
   STEP 7 — SUMMARY
===================================================== */
function renderSummaryUI() {
  const aUser = id("sum_admin_user");
  if (aUser) aUser.textContent = state.admin.username || "—";

  const aEmail = id("sum_admin_email");
  if (aEmail) aEmail.textContent = state.admin.email || "—";

  const db = id("sum_db_name");
  if (db) db.textContent = state.db_name || "—";

  const app = id("sum_app_user");
  if (app) app.textContent = state.app_user_name || "—";
}

/* =====================================================
   STEP 8 — IMPORT
===================================================== */
async function runImport() {
  if (!stepStatus[2] || !stepStatus[3] || !stepStatus[4]) {
    toastError("Configuration incomplète.");
    return;
  }

  const payload = {
    admin: state.admin,
    db_root: state.db_root,
    db_name: state.db_name,
    app_sql_user: state.app_user_name || "b2s_app",
    app_user_password: state.app_user_password,
    services: state.services,
    apply_seed: true
  };

  try {
    await api("/api/import", payload, 30000);
    toastSuccess("Import lancé avec succès.");
    showStep(LAST_STEP);
  } catch (e) {
    toastError(e?.message || "Erreur lors de l'import.");
  }
}

/* =====================================================
   API HELPER
===================================================== */
async function api(path, body, timeout = 8000) {
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
      throw new Error(txt || `Erreur API ${res.status}`);
    }

    return res.json();
  } finally {
    clearTimeout(t);
  }
}

/* =====================================================
   TOASTS
===================================================== */
function toast(msg, type = "info") {
  const c = id("toast-container");
  if (!c) return;

  const d = document.createElement("div");
  d.className = `toast toast-${type}`;
  d.textContent = msg;
  c.appendChild(d);

  setTimeout(() => d.remove(), 3500);
}
const toastError = (m) => toast(m, "error");
const toastSuccess = (m) => toast(m, "success");

/* =====================================================
   INIT
===================================================== */
document.addEventListener("DOMContentLoaded", () => {
  // Restore saved state
  restoreState();

  // Ensure we show a valid step
  if (!STEPS.includes(currentStep)) currentStep = FIRST_STEP;
  showStep(currentStep);

  // Live validations (if fields exist)
  if (id("admin_password")) validateAdminForm();
  if (id("app_user_password")) validateAppUserForm();
});
