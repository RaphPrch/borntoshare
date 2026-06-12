// wizard/js/admin-step.js

import { value } from "./dom.js";
import { state, stepStatus } from "./state.js";
import { computePasswordRules, applyPasswordRules } from "./password.js";
import { updateStepperUI } from "./core.js";

export function validateAdminForm() {
  const username = value("admin_username").trim();
  const email = value("admin_email").trim();
  const pwd = value("admin_password");
  const pwdConfirm = value("admin_password_confirm");

  /* -------------------------------
     Password rules
  -------------------------------- */
  const rules = computePasswordRules(pwd, username);

  // ✅ FIX: correct function signature
  applyPasswordRules(rules, "rule-");

  /* -------------------------------
     Global validation
  -------------------------------- */
  const emailOk = !email || /\S+@\S+\.\S+/.test(email);

  const pwdMatch = !!pwd && pwd === pwdConfirm;
  const mismatchEl = document.getElementById("admin_password_mismatch");
  if (mismatchEl) {
    mismatchEl.style.display = pwdConfirm && !pwdMatch ? "block" : "none";
  }

  const ok =
    Object.values(rules).every(Boolean) &&
    username.length > 0 &&
    emailOk &&
    pwdMatch;

  /* -------------------------------
     UI + state
  -------------------------------- */
  const nextBtn = document.getElementById("admin_next_btn");
  if (nextBtn) nextBtn.disabled = !ok;

  stepStatus[2] = ok;

  if (ok) {
    state.admin = {
      username,
      email,
      password: pwd
    };
  } else {
    // ✅ FIX: reset state when invalid
    state.admin = {
      username: "",
      email: "",
      password: ""
    };
  }

  updateStepperUI();
  return ok;
}
