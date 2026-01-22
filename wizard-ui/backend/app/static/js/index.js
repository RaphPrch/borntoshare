// wizard/js/index.js
import { testDb } from "./db-step.js";
import { validateAdminForm } from "./admin-step.js";
import { validateAppUserForm } from "./appdb-step.js";
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
  if (s === 5) return true;
  return false;
}

function goNext() {
  if (!canGoNext()) {
    logWarn("Blocked nextStep()", { step: getCurrentStep(), stepStatus });
    return;
  }
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

  // ------------------------------------------------------
  // Runtime mode (DEV/PROD) UI
  // ------------------------------------------------------
  (async () => {
    try {
      const res = await fetch("/api/mode");
      const m = await res.json();

      const badge = document.getElementById("wizard_env_badge");
      if (badge) {
        // Badge deliberately hidden in UI (kept for future debug).
        // If you want to re-enable, remove the inline style in index.html.
        badge.textContent = "";
      }

      const isProd = m?.prod === true;

      const applySeedBlock = document.getElementById("apply_seed_block");
      const applySeed = document.getElementById("apply_seed");
      const seedBlock = document.getElementById("seed_prod_block");
      const forceBlock = document.getElementById("force_import_block");
      const forceImport = document.getElementById("force_import");

      // In PROD:
      // - seed is forbidden → hide checkbox and show warning
      // - force_import is required to run import → show the checkbox block
      if (seedBlock) seedBlock.style.display = isProd ? "block" : "none";
      if (applySeedBlock) applySeedBlock.style.display = isProd ? "none" : "block";
      if (applySeed) {
        // Reset on mode load to avoid stale state
        applySeed.checked = false;
        applySeed.disabled = isProd;
      }

      if (forceBlock) forceBlock.style.display = isProd ? "block" : "none";
      if (forceImport) {
        // Reset on mode load
        forceImport.checked = false;
      }
    } catch (e) {
      // Mode endpoint is best-effort
      logWarn("Unable to load /api/mode", { error: String(e) });
    }
  })();

  // STEP 1
  bindClick("btn_start", () => {
    logInfo("Start clicked");
    goNext();
  });

  // STEP 2
  bindClick("btn_prev_2", prevStep);
  bindFormSubmit("form_admin", () => {
    // validateAdminForm already updates stepStatus[2]
    if (validateAdminForm()) goNext();
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
    await testDb();
    // do not auto-next, user clicks "Suivant"
  });
  bindClick("db_next_btn", goNext);

  // STEP 4
  bindClick("btn_prev_4", prevStep);
  bindFormSubmit("form_app_db", () => {
    if (validateAppUserForm()) goNext();
  });
  ["db_name", "app_sql_user", "app_user_password", "app_user_password_confirm"].forEach((id) => {
    const el = document.getElementById(id);
    el?.addEventListener("input", validateAppUserForm);
  });
  validateAppUserForm();

  // STEP 5
  bindClick("btn_prev_5", prevStep);
  bindClick("btn_validate", goNext);

  // STEP 6
  bindClick("btn_prev_6", prevStep);
  bindClick("import_btn", () => runImport());

  // Init
  showStep(1);
});
