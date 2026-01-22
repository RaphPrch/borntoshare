import { state, stepStatus } from "./state.js";
import { api } from "./api.js";

function setStatus(elId, kind, text) {
  const el = document.getElementById(elId);
  if (!el) return;

  const klass =
    kind === "ok"
      ? "b2s-pill b2s-pill--ok"
      : kind === "warn"
        ? "b2s-pill b2s-pill--warn"
        : "b2s-pill b2s-pill--ko";

  el.innerHTML = `<span class="${klass}">${text}</span>`;
}

export function renderSummaryUI() {
  // ------------------------------------------------------
  // Prechecks (best-effort)
  // ------------------------------------------------------
  // Only run if DB step has been validated.
  if (!stepStatus[3] || !state.db_root?.host) {
    setStatus("precheck_db_exists", "warn", "DB non validée");
    setStatus("precheck_user_exists", "warn", "DB non validée");
    return;
  }

  // Async update (non-blocking)
  (async () => {
    try {
      const res = await api(
        "/api/db/precheck",
        {
          host: state.db_root.host,
          port: state.db_root.port,
          user: state.db_root.user,
          password: state.db_root.password,
          db_name: state.db_name,
          app_sql_user: state.app_sql_user,
        },
        8000
      );

      if (res?.db_exists === true) {
        setStatus("precheck_db_exists", "warn", "Oui (sera réutilisée)");
      } else if (res?.db_exists === false) {
        setStatus("precheck_db_exists", "ok", "Non (sera créée)");
      } else {
        setStatus("precheck_db_exists", "warn", "Inconnu");
      }

      if (res?.app_user_exists === true) {
        setStatus("precheck_user_exists", "warn", "Oui (sera réutilisé)");
      } else if (res?.app_user_exists === false) {
        setStatus("precheck_user_exists", "ok", "Non (sera créé)");
      } else {
        setStatus("precheck_user_exists", "warn", "Inconnu");
      }

      // --------------------------------------------------
      // Privileges check (best-effort)
      // --------------------------------------------------
      try {
        const priv = await api(
          "/api/db/privileges-test",
          {
            host: state.db_root.host,
            port: state.db_root.port,
            user: state.db_root.user,
            password: state.db_root.password,
          },
          8000
        );

        const ok = priv?.all_required_ok === true || priv?.privileges?.create_table === true;
        if (ok) {
          setStatus("precheck_privileges", "ok", "OK");
        } else {
          setStatus("precheck_privileges", "warn", "Insuffisants");
        }
      } catch (e) {
        setStatus("precheck_privileges", "warn", "Erreur");
      }
    } catch (e) {
      setStatus("precheck_db_exists", "warn", "Erreur");
      setStatus("precheck_user_exists", "warn", "Erreur");
      setStatus("precheck_privileges", "warn", "Erreur");
      // eslint-disable-next-line no-console
      console.warn("[WIZARD] precheck failed", e);
    }
  })();
}
