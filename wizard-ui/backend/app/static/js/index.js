// wizard/js/index.js
import { testDb } from "./db-step.js";
import { validateAdminForm } from "./admin-step.js";
import { validateAppUserForm } from "./appdb-step.js";
import { validateLoggingDbForm } from "./loggingdb-step.js";
import { runImport } from "./import-step.js";
import { stepStatus } from "./state.js";
import { showStep, nextStep, prevStep, getCurrentStep } from "./core.js";
import { logInfo, logWarn } from "./logger.js";

/* ======================================================
   Guards / State machine (declarative-ish)
   - Keeps numeric steps but enforces rules per transition.
====================================================== */
function canGoNext() {
  const s = getCurrentStep();

  if (s === 1) return true;
  if (s === 2) return !!stepStatus[2];
  if (s === 3) return !!stepStatus[3];
  if (s === 4) return !!stepStatus[4];
  if (s === 5) return !!stepStatus[5];
  if (s === 6) return true;
  return false;
}

function guardMessageForStep(step) {
  if (step === 2) return "Complète le formulaire administrateur pour continuer.";
  if (step === 3) return "Teste d'abord la connexion DB avec des identifiants valides.";
  if (step === 4) return "Renseigne une base applicative et un mot de passe conforme.";
  if (step === 5) return "Renseigne la base logging et un mot de passe conforme.";
  return "Étape incomplète.";
}

function setStepGuard(step, message) {
  const el = document.getElementById(`step_guard_${step}`);
  if (!el) return;
  const msg = String(message || "").trim();
  el.textContent = msg;
  el.style.display = msg ? "block" : "none";
}

function goNext() {
  const s = getCurrentStep();
  if (!canGoNext()) {
    const msg = guardMessageForStep(s);
    setStepGuard(s, msg);
    logWarn("Blocked nextStep()", { step: s, stepStatus, reason: msg });
    return;
  }
  setStepGuard(s, "");
  nextStep();
}

function bindClick(id, fn) {
  const el = document.getElementById(id);
  if (!el) return;
  el.addEventListener("click", fn);
}

function bindFormSubmit(id, fn) {
  const form = document.getElementById(id);
  if (!form) return;
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    fn();
  });
}

/* ======================================================
   INIT / BINDINGS
====================================================== */
document.addEventListener("DOMContentLoaded", () => {
  logInfo("Init wizard");


  // STEP 1
  bindClick("btn_start", () => {
    logInfo("Start clicked");
    goNext();
  });

  // STEP 2
  bindClick("btn_prev_2", prevStep);
  bindFormSubmit("form_admin", () => {
    // validateAdminForm already updates stepStatus[2]
    if (validateAdminForm()) {
      setStepGuard(2, "");
      goNext();
    } else {
      setStepGuard(2, guardMessageForStep(2));
    }
  });

  // Live password rules + enable/disable
  ["admin_username", "admin_email", "admin_password", "admin_password_confirm"].forEach((id) => {
    const el = document.getElementById(id);
    el?.addEventListener("input", validateAdminForm);
  });
  // Ensure initial state reflects defaults
  validateAdminForm();

  // STEP 3
  bindClick("btn_prev_3", prevStep);
  bindFormSubmit("form_db", async () => {
    const ok = await testDb();
    if (ok) {
      setStepGuard(3, "");
      goNext();
    } else {
      setStepGuard(3, guardMessageForStep(3));
    }
  });

  // STEP 4
  bindClick("btn_prev_4", prevStep);
  bindFormSubmit("form_app_db", () => {
    if (validateAppUserForm()) {
      setStepGuard(4, "");
      goNext();
    } else {
      setStepGuard(4, guardMessageForStep(4));
    }
  });
  ["db_name", "app_sql_user", "app_user_password", "app_user_password_confirm"].forEach((id) => {
    const el = document.getElementById(id);
    el?.addEventListener("input", validateAppUserForm);
  });
  validateAppUserForm();

  // STEP 5 (Logging DB)
  bindClick("btn_prev_5", prevStep);
  bindFormSubmit("form_logging_db", () => {
    if (validateLoggingDbForm()) {
      setStepGuard(5, "");
      goNext();
    } else {
      setStepGuard(5, guardMessageForStep(5));
    }
  });
  ["logging_db_name", "logging_sql_user", "logging_user_password", "logging_user_password_confirm"].forEach((id) => {
    const el = document.getElementById(id);
    el?.addEventListener("input", validateLoggingDbForm);
  });
  validateLoggingDbForm();

  // STEP 6 (Validation)
  bindClick("btn_prev_6", prevStep);
  bindClick("btn_validate", () => runImport());

  // Init
  showStep(1);
});
