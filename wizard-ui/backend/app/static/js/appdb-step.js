// wizard/js/app-db-step.js

import { value } from "./dom.js";
import { state, stepStatus } from "./state.js";
import { computePasswordRules, applyPasswordRules } from "./password.js";
import { updateStepperUI } from "./core.js";

export function validateAppUserForm() {
  const dbName = value("db_name").trim();
  const user = value("app_sql_user").trim();
  const pwd = value("app_user_password");
  const pwdConfirm = value("app_user_password_confirm");

  /* -------------------------------
     Password rules
  -------------------------------- */
  const rules = computePasswordRules(pwd);
  applyPasswordRules(rules, "app-rule-");

  /* -------------------------------
     Global validation
  -------------------------------- */
  const ok =
    Object.values(rules).every(Boolean) &&
    dbName.length > 0 &&
    user.length > 0 &&
    /^[a-zA-Z0-9_]+$/.test(user) &&
    user.toLowerCase() !== "root" &&
    !!pwd &&
    pwd === pwdConfirm;

  const mismatchEl = document.getElementById("app_password_mismatch");
  if (mismatchEl) {
    mismatchEl.style.display = pwdConfirm && pwd !== pwdConfirm ? "block" : "none";
  }

  /* -------------------------------
     UI + state
  -------------------------------- */
  const nextBtn = document.getElementById("app_next_btn");
  if (nextBtn) nextBtn.disabled = !ok;

  stepStatus[4] = ok;

  if (ok) {
    state.db_name = dbName;
    state.app_sql_user = user;
    state.app_user_password = pwd;
  } else {
    // ✅ IMPORTANT: reset state if invalid
    state.db_name = "";
    state.app_sql_user = "";
    state.app_user_password = "";
  }

  updateStepperUI();
  return ok;
}
