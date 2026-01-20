/* -----------------------------------------------------
 BornToShare Wizard v5 — JS contrôleur principal
----------------------------------------------------- */

const STORAGE_KEY = "b2s_wizard_state_v1";

let currentStep = 1;
const maxStep = 8;

/* -----------------------------------------------------
   ÉTAT
----------------------------------------------------- */
const state = {
  admin: {},
  db_root: {},
  db_name: "",
  app_user_password: "",
  services: []
};

const stepStatus = {
  1: true,
  2: false,
  3: false,
  4: false
};

/* -----------------------------------------------------
   Helpers
----------------------------------------------------- */
const id = (x) => document.getElementById(x);
const value = (x) => id(x)?.value ?? "";

/* -----------------------------------------------------
   Persistence
----------------------------------------------------- */
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
    Object.assign(state, parsed.state || {});
    Object.assign(stepStatus, parsed.stepStatus || {});
    currentStep = parsed.currentStep || 1;
  } catch {}
}

/* -----------------------------------------------------
   Password rules (PURE)
----------------------------------------------------- */
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

/* -----------------------------------------------------
   Password rules (UI)
----------------------------------------------------- */
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

/* -----------------------------------------------------
   Generic password form validator
----------------------------------------------------- */
function validatePasswordForm({
  password,
  forbiddenValue = "",
  rulePrefix,
  nextButtonId,
  onValid
}) {
  const rules = computePasswordRules(password, forbiddenValue);
  applyPasswordRules({ rules, rulePrefix });

  const ok = Object.values(rules).every(Boolean);

  const btn = id(nextButtonId);
  if (btn) btn.disabled = !ok;

  if (ok && typeof onValid === "function") {
    onValid();
  }

  return ok;
}

/* -----------------------------------------------------
   Admin validation (STEP 2)
----------------------------------------------------- */
function validateAdminForm() {
  const pwd = value("admin_password");
  const user = value("admin_username");

  const ok = validatePasswordForm({
    password: pwd,
    forbiddenValue: user,
    rulePrefix: "rule-",
    nextButtonId: "admin_next_btn",
    onValid: () => {
      state.admin = {
        username: user,
        email: value("admin_email"),
        password: pwd
      };
      stepStatus[2] = true;
    }
  });

  if (!ok) stepStatus[2] = false;
  updateStepperAll();
  updateGlobalStatus();
  return ok;
}

/* -----------------------------------------------------
   App user validation (STEP 4)
----------------------------------------------------- */
function validateAppUserForm() {
  const pwd = value("app_user_password");

  const ok = validatePasswordForm({
    password: pwd,
    rulePrefix: "app-rule-",
    nextButtonId: "app_next_btn",
    onValid: () => {
      state.db_name = value("db_name");
      state.app_user_password = pwd;
      stepStatus[4] = true;
    }
  });

  if (!ok) stepStatus[4] = false;
  updateStepperAll();
  updateGlobalStatus();
  return ok;
}

/* -----------------------------------------------------
   UI hydrate
----------------------------------------------------- */
function hydrateFormFromState() {
  id("admin_username").value = state.admin.username || "";
  id("admin_email").value = state.admin.email || "";
  id("admin_password").value = state.admin.password || "";

  id("db_host").value = state.db_root.host || "";
  id("db_port").value = state.db_root.port || 3306;
  id("db_user").value = state.db_root.user || "";
  id("db_password").value = state.db_root.password || "";

  id("db_name").value = state.db_name || "";
  id("app_user_password").value = state.app_user_password || "";

  validateAdminForm();
  validateAppUserForm();
}

/* -----------------------------------------------------
   Progress / Stepper
----------------------------------------------------- */
function updateProgress() {
  const pct = Math.round(((currentStep - 1) / (maxStep - 1)) * 100);
  id("b2s_progress_bar").style.width = pct + "%";
  id("b2s_progress_label").textContent =
    `Étape ${currentStep} sur ${maxStep}`;
}

function showStep(step) {
  currentStep = step;

  document.querySelectorAll(".b2s-step").forEach(s =>
    s.classList.toggle("active", Number(s.dataset.step) === step)
  );

  document.querySelectorAll(".b2s-stepper li").forEach(li =>
    li.classList.toggle("active", Number(li.dataset.step) === step)
  );

  if (step === 7) renderSummaryUI();

  updateProgress();
  updateStepperAll();
  updateGlobalStatus();
  persistState();
}

/* -----------------------------------------------------
   Stepper
----------------------------------------------------- */
function updateStepperAll() {
  document.querySelectorAll(".b2s-stepper li").forEach(li => {
    const step = Number(li.dataset.step);
    const allowed =
      step === 1 ||
      step <= currentStep ||
      stepStatus[step];

    li.style.opacity = allowed ? "1" : "0.45";
    li.style.cursor = allowed ? "pointer" : "not-allowed";
    li.onclick = allowed ? () => showStep(step) : null;
  });
}

/* -----------------------------------------------------
   Validation
----------------------------------------------------- */
function validateStep(step) {
  if (step === 1) return true;
  if (step === 2) return validateAdminForm();
  if (step === 3 && !stepStatus[3]) {
    toastError("Connexion DB non validée.");
    return false;
  }
  if (step === 4) return validateAppUserForm();
  return true;
}

function nextStep() {
  if (!validateStep(currentStep)) return;
  showStep(currentStep + 1);
}

/* -----------------------------------------------------
   DB test
----------------------------------------------------- */
async function testDb(ev) {
  const btn = ev.target;
  btn.disabled = true;
  btn.textContent = "Connexion en cours…";

  try {
    const cfg = {
      host: value("db_host"),
      port: Number(value("db_port")),
      user: value("db_user"),
      password: value("db_password")
    };

    await api("/api/db/test", cfg);
    state.db_root = cfg;
    stepStatus[3] = true;
    id("db_next_btn").disabled = false;
    toastSuccess("Connexion DB validée.");
  } catch {
    stepStatus[3] = false;
    toastError("Échec du test DB.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Tester la connexion";
    updateStepperAll();
    persistState();
  }
}

/* -----------------------------------------------------
   API
----------------------------------------------------- */
async function api(path, body, timeout = 8000) {
  const ctrl = new AbortController();
  setTimeout(() => ctrl.abort(), timeout);

  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: ctrl.signal
  });

  if (!res.ok) throw new Error("Erreur API");
  return res.json();
}

/* -----------------------------------------------------
   Toasts
----------------------------------------------------- */
function toast(msg, type) {
  const c = id("toast-container");
  const d = document.createElement("div");
  d.className = `toast toast-${type}`;
  d.textContent = msg;
  c.appendChild(d);
  setTimeout(() => d.remove(), 3500);
}
const toastError = m => toast(m, "error");
const toastSuccess = m => toast(m, "success");

/* -----------------------------------------------------
   Init
----------------------------------------------------- */
document.addEventListener("DOMContentLoaded", () => {
  restoreState();
  hydrateFormFromState();
  showStep(currentStep || 1);
});
