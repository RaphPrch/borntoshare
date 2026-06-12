// wizard/js/loggingdb-step.js

import { state, stepStatus } from "./state.js";
import { computePasswordRules, applyPasswordRules } from "./password.js";
import { updateStepperUI } from "./core.js";

export function validateLoggingDbForm() {
  const dbName = (document.getElementById("logging_db_name")?.value || "").trim();
  const user = (document.getElementById("logging_sql_user")?.value || "").trim();
  const pwd = document.getElementById("logging_user_password")?.value || "";
  const pwdConfirm = document.getElementById("logging_user_password_confirm")?.value || "";

  const rules = computePasswordRules(pwd);
  applyPasswordRules(rules, "logging-rule-");

  const ok =
    Object.values(rules).every(Boolean) &&
    dbName.length > 0 &&
    user.length > 0 &&
    /^[a-zA-Z0-9_]+$/.test(user) &&
    user.toLowerCase() !== "root" &&
    !!pwd &&
    pwd === pwdConfirm;

  const mismatchEl = document.getElementById("logging_password_mismatch");
  if (mismatchEl) {
    mismatchEl.style.display = pwdConfirm && pwd !== pwdConfirm ? "block" : "none";
  }

  const nextBtn = document.getElementById("logging_next_btn");
  if (nextBtn) nextBtn.disabled = !ok;

  stepStatus[5] = ok;

  if (ok) {
    state.logging_db = {
      db_name: dbName,
      app_sql_user: user,
      app_user_password: pwd,
    };
  } else {
    state.logging_db = {
      db_name: "",
      app_sql_user: "app_user",
      app_user_password: "",
    };
  }

  updateStepperUI();
  return ok;
}
