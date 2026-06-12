import { toastSuccess, toastError } from "./toast.js";
import { el, value } from "./dom.js";
import { state, stepStatus } from "./state.js";
import { computePasswordRules } from "./password.js";

// --------------------------------------------------
// Run final wizard import
// --------------------------------------------------
export async function runImport() {
  try {
    // ------------------------------------------------
    // Guards (PROD safety + step completeness)
    // ------------------------------------------------
    try {
      const res = await fetch("/api/mode");
      const m = await res.json();

      const isProd = m?.prod === true;

      // Defense-in-depth: even if UI hides/disables, enforce here.
      if (isProd && el("apply_seed")?.checked === true) {
        toastError("Seed interdit en environnement PROD.");
        return;
      }
    } catch (e) {
      console.warn("[WIZARD IMPORT] Unable to load /api/mode", e);
    }

    if (!stepStatus[2] || !stepStatus[3] || !stepStatus[4] || !stepStatus[5]) {
      toastError(
        "Wizard incomplet : valide les étapes Admin / DB / Base applicative / BDD Logging avant l’import."
      );
      return;
    }

    // ------------------------------------------------
    // Collect values (source of truth = state)
    // ------------------------------------------------
    const db_name = state.db_name || value("db_name");

    const db_root = {
      host: state.db_root?.host || value("db_host"),
      port: Number(state.db_root?.port || value("db_port")),
      user: state.db_root?.user || value("db_user"),
      password: state.db_root?.password || value("db_password"),
    };

    const payload = {
      db_name,
      db_root,
      app_sql_user: state.app_sql_user || value("app_sql_user") || "b2s_app",
      app_user_password:
        state.app_user_password || value("app_user_password"),
      admin: {
        username:
          state.admin?.username || value("admin_username") || "admin",
        email: state.admin?.email || value("admin_email") || "",
        password: state.admin?.password || value("admin_password"),
      },
      apply_seed: el("apply_seed")?.checked === true,
      force_import: el("force_import")?.checked === true,
      logging_db: {
        db_name: state.logging_db?.db_name || value("logging_db_name"),
        app_sql_user: state.logging_db?.app_sql_user || value("logging_sql_user") || "app_user",
        app_user_password: state.logging_db?.app_user_password || value("logging_user_password")
      }
    };

    // ------------------------------------------------
    // Front validation (CRITICAL)
    // ------------------------------------------------
    if (!payload.db_name) {
      toastError("Nom de base de données requis.");
      el("db_name")?.focus();
      return;
    }

    if (
      !payload.db_root.host ||
      !payload.db_root.port ||
      !payload.db_root.user ||
      !payload.db_root.password
    ) {
      toastError("Configuration DB root incomplète.");
      el("db_host")?.focus();
      return;
    }

    if (!payload.app_user_password) {
      toastError("Mot de passe du compte SQL applicatif requis.");
      el("app_user_password")?.focus();
      return;
    }

    if (!payload.admin.password) {
      toastError("Mot de passe administrateur requis.");
      el("admin_password")?.focus();
      return;
    }

    if (
      !payload.logging_db?.db_name ||
      !payload.logging_db?.app_sql_user ||
      !payload.logging_db?.app_user_password
    ) {
      toastError("Configuration Base Logging incomplète.");
      return;
    }

    if (
      !Number.isFinite(payload.db_root.port) ||
      payload.db_root.port <= 0
    ) {
      toastError("Port de la base de données invalide.");
      el("db_port")?.focus();
      return;
    }

    const adminPwdRules = computePasswordRules(
      payload.admin.password,
      payload.admin.username
    );
    if (!Object.values(adminPwdRules).every(Boolean)) {
      toastError(
        "Le mot de passe administrateur ne respecte pas les critères."
      );
      el("admin_password")?.focus();
      return;
    }

    const appPwdRules = computePasswordRules(payload.app_user_password);
    if (!Object.values(appPwdRules).every(Boolean)) {
      toastError(
        "Le mot de passe du compte applicatif ne respecte pas les critères."
      );
      el("app_user_password")?.focus();
      return;
    }

    const loggingPwdRules = computePasswordRules(payload.logging_db.app_user_password);
    if (!Object.values(loggingPwdRules).every(Boolean)) {
      toastError(
        "Le mot de passe du compte logging ne respecte pas les critères."
      );
      el("logging_user_password")?.focus();
      return;
    }

    if (payload.admin.email && !isValidEmail(payload.admin.email)) {
      toastError("L'email administrateur n'est pas valide.");
      el("admin_email")?.focus();
      return;
    }

    // ------------------------------------------------
    // Call API
    // ------------------------------------------------
    const response = await fetch("/api/import/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await response.json();

    // ------------------------------------------------
    // Handle response
    // ------------------------------------------------
    if (!response.ok) {
      toastError(data?.detail || "Erreur lors de l'import.");
      return;
    }

    if (data.ok) {
      toastSuccess("✅ Import terminé avec succès");
    } else if (data.skipped) {
      toastError(
        data.message ||
          "Import ignoré (mode PROD – force_import requis)."
      );
    } else {
      toastError("Import échoué. Consulte les logs.");
    }
  } catch (err) {
    console.error("[WIZARD IMPORT ERROR]", err);
    toastError("Erreur réseau ou exception JS.");
  }
}

// --------------------------------------------------
// Utils
// --------------------------------------------------
function isValidEmail(email) {
  const emailPattern =
    /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
  return emailPattern.test(email);
}

// --------------------------------------------------
// Real-time Validation
// --------------------------------------------------
el("db_name")?.addEventListener("input", validateForm);
el("db_host")?.addEventListener("input", validateForm);
el("db_port")?.addEventListener("input", validateForm);
el("db_user")?.addEventListener("input", validateForm);
el("db_password")?.addEventListener("input", validateForm);
el("app_user_password")?.addEventListener("input", validateForm);
el("app_user_password_confirm")?.addEventListener("input", validateForm);
el("admin_password")?.addEventListener("input", validateForm);
el("admin_password_confirm")?.addEventListener("input", validateForm);
el("admin_email")?.addEventListener("input", validateForm);

function validateForm() {
  const appPwdRules = computePasswordRules(value("app_user_password"));
  const adminPwdRules = computePasswordRules(
    value("admin_password"),
    value("admin_username")
  );

  const isFormValid =
    value("db_name") &&
    value("db_host") &&
    value("db_port") &&
    value("db_user") &&
    value("db_password") &&
    value("app_user_password") &&
    value("app_user_password") === value("app_user_password_confirm") &&
    value("admin_password") &&
    value("admin_password") === value("admin_password_confirm") &&
    Object.values(appPwdRules).every(Boolean) &&
    Object.values(adminPwdRules).every(Boolean) &&
    isValidEmail(value("admin_email") || "");

  // volontairement non bloquant (UX)
}

// --------------------------------------------------
// 🔥 MISSING LINK FIX — Button binding
// --------------------------------------------------
el("import_btn")?.addEventListener("click", (e) => {
  e.preventDefault();
  runImport();
});
