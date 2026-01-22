/* -----------------------------------------------------
 BornToShare Wizard v5 — JS contrôleur principal
 GitHub publishable — PROD READY (no secrets persisted)
----------------------------------------------------- */

"use strict";

/* =====================================================
   CONSTANTES & STEPS
===================================================== */
const STORAGE_KEY = "b2s_wizard_state_v5";

/**
 * Steps réellement présents dans l'HTML (version corrigée)
 * 1..6 : Welcome, Admin, DB, App DB, Summary, Import
 */
const STEPS = [1, 2, 3, 4, 5, 6];
const FIRST_STEP = STEPS[0];
const LAST_STEP = STEPS[STEPS.length - 1];

let currentStep = FIRST_STEP;

/* =====================================================
   ÉTAT GLOBAL (⚠️ no secrets should be persisted)
===================================================== */
const state = {
  admin: {
    username: "",
    email: "",
    password: "" // in-memory only
  },
  db_root: {
    host: "",
    port: 3306,
    user: "",
    password: "" // in-memory only
  },
  db_name: "",
  app_sql_user: "b2s_app",
  app_user_password: "", // in-memory only
  services: []
};

/**
 * Validation minimale par step
 */
const stepStatus = {
  1: true,
  2: false,
  3: false,
  4: false,
  5: false,
  6: false
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
   PERSISTENCE (no secrets stored)
===================================================== */
function _redactedStateForStorage() {
  return {
    admin: {
      username: state.admin.username || "",
      email: state.admin.email || ""
      // password intentionally omitted
    },
    db_root: {
      host: state.db_root.host || "",
      port: Number(state.db_root.port || 3306),
      user: state.db_root.user || ""
      // password intentionally omitted
    },
    db_name: state.db_name || "",
    app_sql_user: state.app_sql_user || "b2s_app"
    // app_user_password intentionally omitted
    // services omitted by default (not used in your HTML)
  };
}

function persistState() {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        currentStep,
        state: _redactedStateForStorage(),
        stepStatus
      })
    );
  } catch {}
}

function restoreState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;

    const parsed = JSON.parse(raw);

    // Restore non-secret fields only
    if (parsed?.state?.admin) {
      state.admin.username = String(parsed.state.admin.username || "");
      state.admin.email = String(parsed.state.admin.email || "");
    }
    if (parsed?.state?.db_root) {
      state.db_root.host = String(parsed.state.db_root.host || "");
      state.db_root.port = Number(parsed.state.db_root.port || 3306);
      state.db_root.user = String(parsed.state.db_root.user || "");
    }
    if (typeof parsed?.state?.db_name === "string") state.db_name = parsed.state.db_name;
    if (typeof parsed?.state?.app_sql_user === "string")
      state.app_sql_user = parsed.state.app_sql_user || "b2s_app";

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
    forbidden: forbid ? !pwd.toLowerCase().includes(forbid.toLowerCase()) : true
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

function updateStepperAll() {
  // Recompute summary/import readiness
  stepStatus[5] = !!(stepStatus[2] && stepStatus[3] && stepStatus[4]);
  stepStatus[6] = stepStatus[5];

  document.querySelectorAll(".b2s-stepper li").forEach((li) => {
    const step = Number(li.dataset.step);
    const idx = STEPS.indexOf(step);

    if (idx === -1) {
      li.style.opacity = "0.3";
      li.style.cursor = "not-allowed";
      li.onclick = null;
      return;
    }

    // Allowed if: first step, or already reached, or explicitly validated
    const allowed =
      step === FIRST_STEP ||
      STEPS.indexOf(step) <= STEPS.indexOf(currentStep) ||
      !!stepStatus[step];

    li.style.opacity = allowed ? "1" : "0.45";
    li.style.cursor = allowed ? "pointer" : "not-allowed";
    li.onclick = allowed ? () => showStep(step) : null;
  });
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

  if (currentStep === 5) renderSummaryUI();

  updateProgress();
  updateStepperAll();
  persistState();
}

/* =====================================================
   NAVIGATION
===================================================== */
function validateStep(step) {
  if (step === 1) return true;
  if (step === 2) return validateAdminForm();
  if (step === 3) {
    if (!stepStatus[3]) {
      toastError("Connexion DB non validée. Lance “Tester la connexion”.");
      return false;
    }
    return true;
  }
  if (step === 4) return validateAppUserForm();
  if (step === 5) return stepStatus[5] === true;
  return true;
}

/**
 * Ton HTML appelle onclick="nextStep()"
 */
function nextStep() {
  if (!validateStep(currentStep)) return;

  const idx = STEPS.indexOf(currentStep);
  const next = STEPS[Math.min(idx + 1, STEPS.length - 1)];
  showStep(next);
}

/* =====================================================
   STEP 2 — ADMIN
===================================================== */
function validateAdminForm() {
  const username = String(value("admin_username") || "").trim();
  const email = String(value("admin_email") || "").trim();
  const pwd = String(value("admin_password") || "");

  const rules = computePasswordRules(pwd, username);
  applyPasswordRules({ rules, rulePrefix: "rule-" });

  const emailOk = /\S+@\S+\.\S+/.test(email);
  const ok = Object.values(rules).every(Boolean) && !!username && emailOk;

  const btn = id("admin_next_btn");
  if (btn) btn.disabled = !ok;

  if (ok) {
    state.admin.username = username;
    state.admin.email = email;
    state.admin.password = pwd; // in-memory only
    stepStatus[2] = true;
  } else {
    stepStatus[2] = false;
  }

  updateStepperAll();
  persistState();
  return ok;
}

/* =====================================================
   STEP 4 — APP DB USER
===================================================== */
function validateAppUserForm() {
  const dbName = String(value("db_name") || "").trim();
  const appUser = String(value("app_sql_user") || "b2s_app").trim();
  const pwd = String(value("app_user_password") || "");

  const rules = computePasswordRules(pwd);
  applyPasswordRules({ rules, rulePrefix: "app-rule-" });

  const ok =
    Object.values(rules).every(Boolean) &&
    !!dbName &&
    !!appUser &&
    /^[a-zA-Z0-9_]+$/.test(appUser) &&
    appUser.toLowerCase() !== "root";

  const btn = id("app_next_btn");
  if (btn) btn.disabled = !ok;

  if (ok) {
    state.db_name = dbName;
    state.app_sql_user = appUser;
    state.app_user_password = pwd; // in-memory only
    stepStatus[4] = true;
  } else {
    stepStatus[4] = false;
  }

  updateStepperAll();
  persistState();
  return ok;
}

/* =====================================================
   STEP 3 — TEST DB
===================================================== */
async function testDb(ev) {
  const btn = ev?.target;
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Test en cours…";
  }

  const cfg = {
    host: String(value("db_host") || "").trim(),
    port: Number(value("db_port") || 3306),
    user: String(value("db_user") || "").trim(),
    password: String(value("db_password") || "")
  };

  try {
    if (!cfg.host || !cfg.user) throw new Error("Host et utilisateur DB requis.");

    // 1) Test connexion
    await api("/api/db/test", cfg, 8000);

    // 2) Test droits (si endpoint existe)
    // Si ton backend n'a pas encore cet endpoint, on ne bloque pas :
    // on considère "connexion OK" = step validé (wizard minimal).
    let priv = null;
    try {
      const res = await api("/api/db/privileges-test", cfg, 8000);
      if (res && typeof res === "object") priv = res.privileges || res;
    } catch {
      // ignore (endpoint absent)
    }

    // 3) Wizard state
    state.db_root = cfg; // password in-memory only
    stepStatus[3] = true;

    const nextBtn = id("db_next_btn");
    if (nextBtn) nextBtn.disabled = false;

    // 4) UX (non-root info box if present)
    const isRoot = String(cfg.user || "").toLowerCase() === "root";
    const nonRootInfo = id("db_non_root_warning");
    if (nonRootInfo) {
      nonRootInfo.style.display = !isRoot ? "block" : "none";
    }

    // If privileges provided, optionally show a nicer message
    if (priv && typeof priv === "object") {
      const canCreateTable = !!priv.create_table || !!priv.createTable;
      if (!canCreateTable) {
        // if we can determine it, make it explicit
        toastError("Connexion OK mais droits insuffisants (CREATE TABLE manquant).");
      } else {
        toastSuccess(isRoot ? "DB validée (root)." : "DB validée (non-root).");
      }
    } else {
      toastSuccess(isRoot ? "DB validée (root)." : "DB validée (non-root).");
    }
  } catch (e) {
    stepStatus[3] = false;

    const nextBtn = id("db_next_btn");
    if (nextBtn) nextBtn.disabled = true;

    // Hide non-root info if present
    const nonRootInfo = id("db_non_root_warning");
    if (nonRootInfo) nonRootInfo.style.display = "none";

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
   STEP 5 — SUMMARY
===================================================== */
function renderSummaryUI() {
  const aUser = id("sum_admin_user");
  if (aUser) aUser.textContent = state.admin.username || "—";

  const aEmail = id("sum_admin_email");
  if (aEmail) aEmail.textContent = state.admin.email || "—";

  const db = id("sum_db_name");
  if (db) db.textContent = state.db_name || "—";

  const app = id("sum_app_user");
  if (app) app.textContent = state.app_sql_user || "—";
}

/* =====================================================
   STEP 6 — IMPORT
===================================================== */
let IS_PROD = false;

async function runImport() {
  // Ensure latest validations
  validateAdminForm();
  validateAppUserForm();

  if (!stepStatus[2] || !stepStatus[3] || !stepStatus[4]) {
    toastError("Configuration incomplète (admin, DB et base applicative).");
    return;
  }

  const applySeed = !!id("apply_seed")?.checked;

  // Backend already blocks seed in PROD, but UI should be strict too.
  if (IS_PROD && applySeed) {
    toastError("Seed interdit en PROD.");
    return;
  }

  // Optional checkbox (not present in your HTML). If you add it later, it will work.
  const forceImport = !!id("force_import")?.checked;

  if (IS_PROD && !forceImport) {
    toastError("Import bloqué en PROD : force_import requis.");
    return;
  }

  const payload = {
    admin: {
      username: state.admin.username,
      email: state.admin.email,
      password: state.admin.password // sent once
    },
    db_root: {
      host: state.db_root.host,
      port: state.db_root.port,
      user: state.db_root.user,
      password: state.db_root.password // sent once
    },
    db_name: state.db_name,
    app_sql_user: state.app_sql_user || "b2s_app",
    app_user_password: state.app_user_password, // sent once
    services: state.services,
    apply_seed: applySeed,
    force_import: forceImport
  };

  const importBtn = id("import_btn");
  if (importBtn) {
    importBtn.disabled = true;
    importBtn.textContent = "Import en cours…";
  }

  try {
    const res = await api("/api/import/", payload, 30000);

    if (res?.skipped) {
      toastError(res.message || "Import ignoré.");
      return;
    }

    toastSuccess(res.message || "Import terminé.");

    // After a successful import, purge secrets from memory + storage
    state.admin.password = "";
    state.db_root.password = "";
    state.app_user_password = "";
    persistState();
  } catch (e) {
    toastError(e?.message || "Erreur lors de l'import.");
  } finally {
    if (importBtn) {
      importBtn.disabled = false;
      importBtn.textContent = "Lancer l’import";
    }
  }
}

/* =====================================================
   API HELPER (POST JSON)
===================================================== */
async function api(path, body, timeout = 8000) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeout);

  try {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
      signal: ctrl.signal
    });

    if (!res.ok) {
      const txt = await res.text();

      // Try to extract FastAPI-like messages
      try {
        const j = JSON.parse(txt);
        if (j?.detail) throw new Error(String(j.detail));
        if (j?.message) throw new Error(String(j.message));
      } catch {
        // ignore JSON parse errors
      }

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
   MODE / SEED GUARD (PROD SAFE)
===================================================== */
async function initWizardMode() {
  try {
    const res = await fetch("/api/mode", { method: "GET" });
    const data = await res.json();

    // Support both shapes:
    // - { prod: true }
    // - { mode: "prod" | "dev" }
    IS_PROD = !!data?.prod || String(data?.mode || "").toLowerCase() === "prod";

    const seedCheckbox = id("apply_seed");
    const seedLabel = id("seed_label");
    const seedBlock = id("seed_prod_block");
    const badge = id("wizard_env_badge");

    if (badge) {
      badge.textContent = IS_PROD ? "Wizard v5.0 — PROD" : "Wizard v5.0 — DEV";
      badge.classList.toggle("is-prod", IS_PROD);
    }

    if (IS_PROD && seedCheckbox) {
      seedCheckbox.checked = false;
      seedCheckbox.disabled = true;

      if (seedLabel) {
        seedLabel.style.opacity = "0.5";
        seedLabel.style.cursor = "not-allowed";
      }
      if (seedBlock) seedBlock.style.display = "block";
    } else {
      if (seedBlock) seedBlock.style.display = "none";
    }
  } catch {
    // Safe fallback: disable seed
    const seedCheckbox = id("apply_seed");
    if (seedCheckbox) {
      seedCheckbox.checked = false;
      seedCheckbox.disabled = true;
    }
    const seedBlock = id("seed_prod_block");
    if (seedBlock) {
      seedBlock.style.display = "block";
      seedBlock.textContent = "ℹ️ Impossible de déterminer le mode : seed désactivé par sécurité.";
    }
  }
}

/* =====================================================
   INIT
===================================================== */
function hydrateUIFromState() {
  // Admin
  if (id("admin_username")) setValue("admin_username", state.admin.username || "admin");
  if (id("admin_email")) setValue("admin_email", state.admin.email || "admin@local");
  // Do not restore passwords

  // DB root
  if (id("db_host")) setValue("db_host", state.db_root.host || "");
  if (id("db_port")) setValue("db_port", state.db_root.port || 3306);
  if (id("db_user")) setValue("db_user", state.db_root.user || "wizard");
  // Do not restore db password

  // App DB
  if (id("db_name")) setValue("db_name", state.db_name || "");
  if (id("app_sql_user")) setValue("app_sql_user", state.app_sql_user || "b2s_app");
  // Do not restore app password
}

document.addEventListener("DOMContentLoaded", async () => {
  restoreState();
  hydrateUIFromState();

  await initWizardMode();

  // Show a valid step
  if (!STEPS.includes(currentStep)) currentStep = FIRST_STEP;
  showStep(currentStep);

  // Run validations if inputs are present
  if (id("admin_password")) validateAdminForm();
  if (id("app_user_password")) validateAppUserForm();

  updateStepperAll();
  updateProgress();
});

/* =====================================================
   Expose functions for inline HTML onclick handlers
===================================================== */
window.nextStep = nextStep;
window.validateAdminForm = validateAdminForm;
window.validateAppUserForm = validateAppUserForm;
window.testDb = testDb;
window.runImport = runImport;
window.showStep = showStep;
