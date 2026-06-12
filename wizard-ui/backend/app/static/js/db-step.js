// wizard/js/db-step.js

import { stepStatus, state } from "./state.js";
import { toastSuccess, toastError } from "./toast.js";
import { updateStepperUI } from "./core.js";
import { api } from "./api.js"; // ✅ CORRECT

/**
 * Teste la connexion DB avec diagnostics progressifs.
 * Résultats uniquement via Toast + logs console.
 */
export async function testDb() {
  const host = document.getElementById("db_host")?.value.trim();
  const port = Number(document.getElementById("db_port")?.value || 3306);
  const user = document.getElementById("db_user")?.value.trim();
  const password = document.getElementById("db_password")?.value || "";

  if (!host || !user) {
    stepStatus[3] = false;
    updateStepperUI();
    toastError("Host et utilisateur DB requis.");
    return false;
  }

  console.group("[WIZARD][DB TEST]");
  console.log("Host:", host);
  console.log("Port:", port);
  console.log("User:", user);

  try {
    /* =====================================================
       1️⃣ DNS / TCP (OPTIONNEL)
    ===================================================== */
    try {
      console.log("→ DNS / TCP diagnostic…");
      const diag = await api("/api/db/diagnostic", { host, port }, 12000);

      if (diag?.dns_ok === false) {
        stepStatus[3] = false;
        updateStepperUI();
        toastError("DNS introuvable pour le host.");
        console.error("DNS FAILED");
        return false;
      }

      if (diag?.tcp_ok === false) {
        stepStatus[3] = false;
        updateStepperUI();
        toastError(`Port ${port} inaccessible (TCP).`);
        console.error("TCP FAILED");
        return false;
      }

      console.log("DNS OK / TCP OK");
    } catch (e) {
      // Endpoint optionnel
      console.warn("Diagnostic DNS/TCP non disponible, poursuite du test.", e);
    }

    /* =====================================================
       2️⃣ SQL AUTH
    ===================================================== */
    console.log("→ SQL auth test…");
    await api("/api/db/test", { host, port, user, password }, 20000);
    console.log("SQL AUTH OK");

    /* =====================================================
       3️⃣ SQL PRIVILEGES (OPTIONNEL)
    ===================================================== */
    try {
      console.log("→ SQL privileges test…");
      const res = await api(
        "/api/db/privileges-test",
        { host, port, user, password },
        20000
      );

      const priv = res?.privileges || res;
      if (priv?.create_table === false) {
        stepStatus[3] = false;
        updateStepperUI();
        toastError(
          "Connexion OK mais droits SQL insuffisants (CREATE TABLE requis)."
        );
        console.warn("PRIVILEGES INSUFFICIENTS");
        return false;
      }

      console.log("SQL PRIVILEGES OK");
    } catch (e) {
      console.warn("Test des privilèges ignoré ou indisponible.", e);
    }

    /* =====================================================
       ✅ SUCCESS
    ===================================================== */
    state.db_root = { host, port, user, password }; // password = mémoire uniquement
    stepStatus[3] = true;

    const nextBtn = document.getElementById("db_next_btn");
    if (nextBtn) nextBtn.disabled = false;

    toastSuccess("Connexion DB validée.");
    console.log("DB STEP VALIDATED");
    return true;

  } catch (e) {
    console.error("DB TEST FAILED", e);

    stepStatus[3] = false;
    const nextBtn = document.getElementById("db_next_btn");
    if (nextBtn) nextBtn.disabled = true;

    toastError(e?.message || "Connexion DB impossible.");
    return false;
  } finally {
    updateStepperUI();
    console.groupEnd();
  }
}
