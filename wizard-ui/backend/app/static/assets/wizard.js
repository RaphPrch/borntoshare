/* -----------------------------------------------------
 BornToShare Wizard v4.8 — JS contrôleur principal (V5)
 Cohérence avec :
 - gateway-service (B2S_SECURITY_MODE, CORS, etc.)
 - auth-service / governance-service modernisés
 - runtime manifest + Ansible generator
 - V5 : panneau d'édition + test de ports
----------------------------------------------------- */

const STORAGE_KEY = "b2s_wizard_state_v1";

let currentStep = 1;
const maxStep = 13;
let wizardMode = "dev"; // "dev" ou "prod"

const state = {
  admin: {},
  db_root: {},
  db_name: "",
  app_user_password: "",
  services: [],
  syslog: {},
  smtp: {},
  idp: {},
  domain: { dcs: [] }
};

let dcs = [];

/* -----------------------------------------------------
   Helpers
----------------------------------------------------- */
function id(x) { return document.getElementById(x); }
function value(x) { const el = id(x); return el ? el.value : ""; }

/* -----------------------------------------------------
   Chargement du mode (dev/prod)
----------------------------------------------------- */
async function loadMode() {
  try {
    const res = await fetch("/api/mode");
    const data = await res.json();
    wizardMode = data.mode || "dev";

    const badge = id("b2s_mode_badge");
    if (badge) {
      if (wizardMode === "prod") {
        badge.textContent = "Mode PROD – déploiement via Ansible";
        badge.classList.remove("b2s-mode-badge--dev");
        badge.classList.add("b2s-mode-badge--prod");
      } else {
        badge.textContent = "Mode DEV – actions en live";
        badge.classList.remove("b2s-mode-badge--prod");
        badge.classList.add("b2s-mode-badge--dev");
      }
    }
  } catch {
    console.warn("[WIZARD] Impossible de récupérer le mode, fallback dev");
    wizardMode = "dev";
  }
}

/* -----------------------------------------------------
   Persistence localStorage
----------------------------------------------------- */
function persistState() {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ currentStep, state })
    );
  } catch {
    // no-op
  }
}

function restoreState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const payload = JSON.parse(raw);

    if (payload.state) {
      Object.assign(state, payload.state);
      if (payload.state.domain?.dcs) {
        dcs = payload.state.domain.dcs.slice();
      }
    }
    if (payload.currentStep) currentStep = payload.currentStep;
  } catch {
    // no-op
  }
}

/* -----------------------------------------------------
   Hydrate UI depuis state
----------------------------------------------------- */
function setIfExists(fieldId, val) {
  const el = id(fieldId);
  if (el != null && val != null) el.value = val;
}

function hydrateFormFromState() {
  // Admin
  setIfExists("admin_username", state.admin.username);
  setIfExists("admin_email", state.admin.email);
  setIfExists("admin_password", state.admin.password);

  // DB root
  if (state.db_root) {
    setIfExists("db_host", state.db_root.host);
    setIfExists("db_port", state.db_root.port);
    setIfExists("db_user", state.db_root.user);
    setIfExists("db_password", state.db_root.password);
  }

  // DB name / app_user
  setIfExists("db_name", state.db_name);
  setIfExists("app_user_password", state.app_user_password);

  // Syslog
  if (state.syslog) {
    setIfExists("syslog_name", state.syslog.name);
    setIfExists("syslog_host", state.syslog.host);
    setIfExists("syslog_port", state.syslog.port);
    if (id("syslog_proto")) {
      id("syslog_proto").value = state.syslog.protocol || "udp";
    }
  }

  // SMTP
  if (state.smtp) {
    setIfExists("smtp_host", state.smtp.host);
    setIfExists("smtp_port", state.smtp.port);
    setIfExists("smtp_from", state.smtp.from_addr);
    setIfExists("smtp_user", state.smtp.username);
    setIfExists("smtp_pass", state.smtp.password);
    if (id("smtp_tls")) {
      id("smtp_tls").checked = !!state.smtp.use_tls;
    }
  }

  // IdP
  if (state.idp) {
    setIfExists("idp_url", state.idp.url);
    setIfExists("idp_realm", state.idp.realm);
    setIfExists("idp_client_id", state.idp.client_id);
    setIfExists("idp_client_secret", state.idp.client_secret);
  }

  // Domaines
  if (state.domain) {
    setIfExists("dom_name", state.domain.name);
    setIfExists("dom_dns", state.domain.dns);
    setIfExists("dom_forest", state.domain.forest);
  }
}

/* -----------------------------------------------------
   Stepper + Progress
----------------------------------------------------- */
function updateProgress() {
  const bar = id("b2s_progress_bar");
  const label = id("b2s_progress_label");
  const pct = Math.round((currentStep - 1) / (maxStep - 1) * 100);

  if (bar) bar.style.width = pct + "%";
  if (label) label.textContent = `Étape ${currentStep} sur ${maxStep}`;
}

function showStep(step) {
  currentStep = step;

  document.querySelectorAll(".b2s-step").forEach((sec) => {
    sec.classList.toggle("active", Number(sec.dataset.step) === step);
  });

  document.querySelectorAll(".b2s-stepper li").forEach((li) => {
    li.classList.toggle("active", Number(li.dataset.step) === step);
  });

  updateProgress();
  persistState();
  updateJsonPreview();
}

function onStepperClick(e) {
  const li = e.target.closest("li[data-step]");
  if (!li) return;

  const targetStep = Number(li.dataset.step);

  if (wizardMode === "prod") {
    if (targetStep > currentStep) {
      if (!validateStep(currentStep)) {
        toastError("Corrigez cette étape avant d'avancer.");
        return;
      }
      if (targetStep > currentStep + 1) {
        toastWarning("Impossible de sauter des étapes en mode production.");
        return;
      }
      showStep(currentStep + 1);
      return;
    }
  }

  showStep(targetStep);
}

function nextStep() {
  if (wizardMode === "prod" && !validateStep(currentStep)) return;
  if (currentStep < maxStep) showStep(currentStep + 1);
}

/* -----------------------------------------------------
   Validation
----------------------------------------------------- */
function validateAdminPassword(pwd) {
  if (!pwd || pwd.length < 12) {
    toastError("Le mot de passe admin doit contenir au moins 12 caractères.");
    return false;
  }
  const ok =
    /[A-Z]/.test(pwd) &&
    /[a-z]/.test(pwd) &&
    /[0-9]/.test(pwd) &&
    /[^A-Za-z0-9]/.test(pwd);

  if (!ok) {
    toastError("Le mot de passe doit contenir majuscules, minuscules, chiffres, caractères spéciaux.");
  }
  return ok;
}

function validateStep(step) {
  // Étape 2 : Admin
  if (step === 2) {
    if (!value("admin_username") || !value("admin_password")) {
      toastError("Nom d'utilisateur et mot de passe admin requis.");
      return false;
    }
    if (!validateAdminPassword(value("admin_password"))) return false;

    state.admin = {
      username: value("admin_username"),
      email: value("admin_email"),
      password: value("admin_password")
    };
  }

  // Étape 3 : DB root validée
  if (step === 3) {
    if (!state.db_root.host) {
      toastError("Testez et validez la connexion DB avant de continuer.");
      return false;
    }
  }

  // Étape 4 : nom de base
  if (step === 4 && !value("db_name")) {
    toastError("Nom de base requis.");
    return false;
  }

  // Étape 6 : validation des ports en mode PROD
  if (step === 6 && wizardMode === "prod") {
    const notOk = (state.services || []).filter(
      (s) => !s.port || !s.port_ok
    );
    if (notOk.length > 0) {
      toastError("Tous les ports des services doivent être testés et OK avant de continuer (mode PROD).");
      return false;
    }
  }

  return true;
}

/* -----------------------------------------------------
   HTTP helper
----------------------------------------------------- */
async function api(path, body) {
  try {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      return {
        ok: false,
        error: data.detail || data.message || res.statusText
      };
    }

    return {
      ok: true,
      data
    };
  } catch (e) {
    return {
      ok: false,
      error: e.message || "Erreur réseau"
    };
  }
}



/* -----------------------------------------------------
   Toasts
----------------------------------------------------- */
function makeToast(message, kind = "info", timeout = 3500) {
  const c = id("toast-container");
  if (!c) return;

  const div = document.createElement("div");
  div.className = "toast toast-" + kind;
  div.textContent = message;
  c.appendChild(div);

  setTimeout(() => {
    div.style.opacity = "0";
    div.style.transform = "translateX(25px)";
    setTimeout(() => div.remove(), 200);
  }, timeout);
}

const toastSuccess = (m) => makeToast(m, "success");
const toastError = (m) => makeToast(m, "error");
const toastInfo = (m) => makeToast(m, "info");
const toastWarning = (m) => makeToast(m, "warning");

/* -----------------------------------------------------
   JSON Panel
----------------------------------------------------- */
function getSummary() {
  return {
    admin: state.admin,
    db_root: state.db_root,
    db_name: state.db_name,
    app_user_password: state.app_user_password,
    services: state.services,
    syslog: state.syslog,
    smtp: state.smtp,
    idp: state.idp,
    domain: state.domain
  };
}

function updateJsonPreview() {
  const el = id("json_live");
  if (el) el.textContent = JSON.stringify(getSummary(), null, 2);
}

function toggleJsonPanel() {
  const p = id("json_panel");
  if (!p) return;
  p.classList.toggle("open");
  if (p.classList.contains("open")) updateJsonPreview();
}

/* -----------------------------------------------------
   DB TEST
----------------------------------------------------- */
async function testDb() {
  const cfg = {
    host: value("db_host"),
    port: value("db_port"),
    user: value("db_user"),
    password: value("db_password")
  };

  toastInfo("Test de connexion DB...");
  const res = await api("/api/db/test", cfg);

  if (res.ok) {
    // ✅ PERSISTENCE DE L'ÉTAT (MANQUANT)
    state.db_root = cfg;
    persistState();

    toastSuccess(res.data.message || "Connexion DB OK.");
  } else {
    toastError(res.error || "Connexion DB échouée.");
  }
}


/* -----------------------------------------------------
   Services / Ports
----------------------------------------------------- */
function renderServiceAccounts() {
  const root = id("services_accounts");
  if (!root) return;
  root.innerHTML = "";

  (state.services || []).forEach((svc, i) => {
    const row = document.createElement("div");
    row.className = "svc-row";
    row.innerHTML = `
      <span>${svc.name}</span>
      <input placeholder="db_user" value="${svc.db_user || ""}" data-i="${i}" data-k="db_user" />
      <input placeholder="password" type="password" value="${svc.db_password || ""}" data-i="${i}" data-k="db_password" />
    `;
    root.appendChild(row);
  });
}

function renderServicePorts() {
  const root = id("services_ports");
  if (!root) return;
  root.innerHTML = "";

  (state.services || []).forEach((svc, i) => {
    const row = document.createElement("div");
    row.className = "svc-row";
    row.innerHTML = `
      <span>${svc.name}</span>
      <input type="number" value="${svc.port || 0}" data-i="${i}" data-k="port" />
    `;
    root.appendChild(row);
  });
}

function initServiceAccounts() {
  state.services = [
    { name: "auth-service", db_user: "auth_user", db_password: "" },
    { name: "governance-service", db_user: "gov_user", db_password: "" },
    { name: "gateway-service", db_user: "gateway_user", db_password: "" }
  ];
  renderServiceAccounts();
  persistState();
}

function initServicePorts() {
  if (!state.services || state.services.length === 0) {
    initServiceAccounts();
  }

  const defaults = {
    "auth-service": 8000,
    "governance-service": 8001,
    "gateway-service": 9000
  };

  state.services = state.services.map((s) => ({
    ...s,
    port: s.port || defaults[s.name] || 0
  }));

  renderServicePorts();
  persistState();
}

/* -----------------------------------------------------
   Écouteur global input (services + DCs)
----------------------------------------------------- */
document.addEventListener("input", (e) => {
  const i = e.target.dataset.i;
  const k = e.target.dataset.k;

  if (i !== undefined && k && state.services[i]) {
    state.services[i][k] = e.target.value;
    persistState();
  }

  if (i !== undefined && k && String(k).endsWith("_dc")) {
    const key = k.replace("_dc", "");
    dcs[i][key] = e.target.value;
    state.domain.dcs = dcs.slice();
    persistState();
  }
});

/* -----------------------------------------------------
   Résumé + Import
----------------------------------------------------- */
function updateSummary() {
  state.admin = {
    username: value("admin_username"),
    email: value("admin_email"),
    password: value("admin_password")
  };

  state.db_name = value("db_name");
  state.app_user_password = value("app_user_password");

  const el = id("summary_json");
  if (el) el.textContent = JSON.stringify(getSummary(), null, 2);

  persistState();
  updateJsonPreview();
}

/* -----------------------------------------------------
   IMPORT / DEPLOY
----------------------------------------------------- */
async function runImport() {
  // 🔒 VALIDATION FINALE OBLIGATOIRE
  if (!state.db_root || !state.db_root.host) {
    toastError("La connexion à la base de données est obligatoire pour l’import.");
    return;
  }

  const dbName = value("db_name");
  if (!dbName) {
    toastError("Le nom de la base de données est obligatoire pour l’import.");
    return;
  }

  // 🔄 Synchronisation explicite
  state.db_name = dbName;

  updateSummary();

  const res = await api("/api/import/", {
    admin: state.admin,
    db_root: state.db_root,
    db_name: state.db_name,
    services: state.services,
    app_user_password: state.app_user_password
  });

  if (res.ok) {
    toastSuccess(res.data?.message || "Import terminé.");
  } else {
    toastError(res.error || "Erreur lors de l'import.");
  }
}

/* -----------------------------------------------------
   SYSLOG / SMTP / IDP / DOMAIN
   (DB obligatoire ici aussi)
----------------------------------------------------- */
function requireDbOrFail() {
  if (!state.db_root?.host || !state.db_name) {
    toastError("Configuration base de données requise avant cette action.");
    return false;
  }
  return true;
}

async function saveSyslog() {
  if (!requireDbOrFail()) return;

  state.syslog = {
    name: value("syslog_name"),
    host: value("syslog_host"),
    port: value("syslog_port"),
    protocol: value("syslog_proto")
  };

  const res = await api("/api/syslog/save", {
    ...state.syslog,
    db_name: state.db_name,
    root: state.db_root
  });

  if (res.ok) toastSuccess(res.message || "Paramètres Syslog enregistrés.");
  else toastError(res.error || "Erreur lors de l'enregistrement Syslog.");

  persistState();
}

async function saveSMTP() {
  if (!requireDbOrFail()) return;

  state.smtp = {
    host: value("smtp_host"),
    port: value("smtp_port"),
    from_addr: value("smtp_from"),
    username: value("smtp_user"),
    password: value("smtp_pass"),
    use_tls: id("smtp_tls")?.checked
  };

  const res = await api("/api/smtp/save", {
    ...state.smtp,
    db_name: state.db_name,
    root: state.db_root
  });

  if (res.ok) toastSuccess(res.message || "Paramètres SMTP enregistrés.");
  else toastError(res.error || "Erreur lors de l'enregistrement SMTP.");

  persistState();
}

async function saveIdP() {
  if (!requireDbOrFail()) return;

  state.idp = {
    url: value("idp_url"),
    realm: value("idp_realm"),
    client_id: value("idp_client_id"),
    client_secret: value("idp_client_secret")
  };

  const res = await api("/api/idp/save", {
    ...state.idp,
    db_name: state.db_name,
    root: state.db_root
  });

  if (res.ok) toastSuccess(res.message || "Paramètres IdP enregistrés.");
  else toastError(res.error || "Erreur lors de l'enregistrement IdP.");

  persistState();
}

/* ---- DOMAINES / DCs ---- */
function addDC() {
  dcs.push({ fqdn: "", ip: "", site: "" });
  state.domain.dcs = dcs.slice();
  renderDCs();
  persistState();
}

function renderDCs() {
  const root = id("dc_list");
  if (!root) return;
  root.innerHTML = "";

  dcs.forEach((dc, i) => {
    const row = document.createElement("div");
    row.className = "dc-row";
    row.innerHTML = `
      <input placeholder="FQDN" value="${dc.fqdn || ""}" data-i="${i}" data-k="fqdn_dc" />
      <input placeholder="IP" value="${dc.ip || ""}" data-i="${i}" data-k="ip_dc" />
      <input placeholder="Site" value="${dc.site || ""}" data-i="${i}" data-k="site_dc" />
    `;
    root.appendChild(row);
  });
}

async function saveDomain() {
  if (!requireDbOrFail()) return;

  state.domain = {
    name: value("dom_name"),
    dns: value("dom_dns"),
    forest: value("dom_forest"),
    dcs: dcs.slice()
  };

  const res = await api("/api/domain/save", {
    ...state.domain,
    db_name: state.db_name,
    root: state.db_root
  });

  if (res.ok) toastSuccess(res.message || "Domaine AD enregistré.");
  else toastError(res.error || "Erreur lors de l'enregistrement du domaine.");

  persistState();
}

/* -----------------------------------------------------
   EXPORT / ANSIBLE
----------------------------------------------------- */
function exportConfig() {
  updateSummary();

  const data = JSON.stringify(getSummary(), null, 2);
  const a = document.createElement("a");
  a.href = "data:application/json;charset=utf-8," + encodeURIComponent(data);
  a.download = "born_to_share_wizard_config.json";
  a.click();

  const final = id("final_json");
  if (final) final.textContent = data;
}

async function downloadAnsiblePack() {
  if (!requireDbOrFail()) return;

  updateSummary();

  const res = await api("/api/runtime/generate-ansible", getSummary());
  if (res.ok) toastSuccess(res.message || "Pack Ansible généré.");
  else toastError(res.error || "Erreur lors de la génération du pack Ansible.");
}

async function triggerAnsibleDeploy() {
  const res = await api("/api/runtime/trigger-deploy");
  if (res.ok) toastSuccess(res.message || "Signal de déploiement créé.");
  else toastError(res.error || "Erreur lors de l'écriture du signal de déploiement.");
}

/* -----------------------------------------------------
   EDITOR PANEL (V5)
----------------------------------------------------- */
function openEditorPanel(section) {
  const panel = id("editor_panel");
  const ov = id("editor_overlay");
  const title = id("editor_title");
  const content = id("editor_content");

  // Si le HTML n'intègre pas encore le panel → on ne casse pas tout
  if (!panel || !ov || !title || !content) {
    toastWarning("Panneau d'édition non disponible dans cette version du wizard.");
    return;
  }

  panel.classList.add("open");
  ov.classList.add("open");

  title.textContent = "Édition : " + section;

  if (section === "services")      renderEditorServices(content);
  else if (section === "smtp")    renderEditorSMTP(content);
  else if (section === "syslog")  renderEditorSyslog(content);
  else if (section === "domain")  renderEditorDomain(content);
  else                            content.innerHTML = "<p>Aucun éditeur disponible.</p>";
}

function closeEditorPanel() {
  const panel = id("editor_panel");
  const ov = id("editor_overlay");
  if (panel) panel.classList.remove("open");
  if (ov) ov.classList.remove("open");
}

/* ------------------- SERVICES ------------------- */
function renderEditorServices(el) {
  el.innerHTML = `
    <h3>Services & Ports</h3>
    ${
      (state.services || [])
        .map(
          (s, i) => `
      <div class="svc-card">
        <h4>${s.name}</h4>

        <label>Host</label>
        <input data-i="${i}" data-k="host" value="${s.host || "localhost"}" />

        <label>Port d'écoute</label>
        <input type="number" data-i="${i}" data-k="port" value="${s.port || ""}" />

        <label>DB User</label>
        <input data-i="${i}" data-k="db_user" value="${s.db_user || ""}" />

        <label>Password</label>
        <input type="password" data-i="${i}" data-k="db_password" value="${s.db_password || ""}" />

        <button class="b2s-btn-small" onclick="testPort(${i})">
          Tester le port
        </button>
        ${
          s.port_ok
            ? `<span class="port-status port-status--ok">OK (${s.latency_ms || "?"} ms)</span>`
            : `<span class="port-status port-status--pending">Non testé / KO</span>`
        }
      </div>
    `
        )
        .join("")
    }
  `;
}

/* ------------------- SMTP ------------------- */
function renderEditorSMTP(el) {
  el.innerHTML = `
    <h3>Configuration SMTP</h3>

    <label>Serveur</label>
    <input id="edit_smtp_host" value="${state.smtp.host || ""}" />

    <label>Port</label>
    <input id="edit_smtp_port" type="number" value="${state.smtp.port || 587}" />

    <label>From</label>
    <input id="edit_smtp_from" value="${state.smtp.from_addr || ""}" />

    <button class="b2s-btn" onclick="applySMTPSettings()">Appliquer</button>
  `;
}

function applySMTPSettings() {
  state.smtp.host = id("edit_smtp_host").value;
  state.smtp.port = Number(id("edit_smtp_port").value);
  state.smtp.from_addr = id("edit_smtp_from").value;
  persistState();
  hydrateFormFromState();
  toastSuccess("SMTP mis à jour");
}

/* ------------------- SYSLOG ------------------- */
function renderEditorSyslog(el) {
  el.innerHTML = `
    <h3>Configuration Syslog</h3>

    <label>Nom</label>
    <input id="edit_syslog_name" value="${state.syslog.name || ""}" />

    <label>Host</label>
    <input id="edit_syslog_host" value="${state.syslog.host || ""}" />

    <label>Port</label>
    <input id="edit_syslog_port" type="number" value="${state.syslog.port || 514}" />

    <label>Protocole</label>
    <select id="edit_syslog_proto">
      <option value="udp" ${state.syslog.protocol === "udp" ? "selected" : ""}>UDP</option>
      <option value="tcp" ${state.syslog.protocol === "tcp" ? "selected" : ""}>TCP</option>
    </select>

    <button class="b2s-btn" onclick="applySyslogSettings()">Appliquer</button>
  `;
}

function applySyslogSettings() {
  state.syslog = {
    name: id("edit_syslog_name").value,
    host: id("edit_syslog_host").value,
    port: Number(id("edit_syslog_port").value),
    protocol: id("edit_syslog_proto").value
  };
  persistState();
  hydrateFormFromState();
  toastSuccess("Syslog mis à jour");
}

/* ------------------- DOMAIN ------------------- */
function renderEditorDomain(el) {
  el.innerHTML = `
    <h3>Domaine AD</h3>

    <label>Nom</label>
    <input id="edit_dom_name" value="${state.domain.name || ""}" />

    <label>DNS</label>
    <input id="edit_dom_dns" value="${state.domain.dns || ""}" />

    <label>Forêt</label>
    <input id="edit_dom_forest" value="${state.domain.forest || ""}" />

    <h4>Contrôleurs</h4>
    <div>${renderEditorDCs()}</div>

    <button class="b2s-btn-small" onclick="addDC(); openEditorPanel('domain')">+ Ajouter un DC</button>

    <button class="b2s-btn" onclick="applyDomainSettings()">Appliquer</button>
  `;
}

function renderEditorDCs() {
  return (dcs || [])
    .map(
      (dc, i) => `
    <div class="svc-card">
      <input placeholder="FQDN" data-i="${i}" data-k="fqdn_dc" value="${dc.fqdn || ""}" />
      <input placeholder="IP" data-i="${i}" data-k="ip_dc" value="${dc.ip || ""}" />
      <input placeholder="Site" data-i="${i}" data-k="site_dc" value="${dc.site || ""}" />
    </div>
  `
    )
    .join("");
}

function applyDomainSettings() {
  state.domain = {
    name: id("edit_dom_name").value,
    dns: id("edit_dom_dns").value,
    forest: id("edit_dom_forest").value,
    dcs: dcs.slice()
  };
  persistState();
  hydrateFormFromState();
  renderDCs();
  toastSuccess("Domaine mis à jour");
}

/* -----------------------------------------------------
   TEST PORT TCP (V5)
----------------------------------------------------- */
async function testPort(index) {
  const svc = state.services[index];
  if (!svc) {
    toastError("Service introuvable pour le test de port.");
    return;
  }

  const host = svc.host || "localhost";
  const port = Number(svc.port || 0);

  if (!port) {
    toastError("Port invalide.");
    return;
  }

  toastInfo(`Test du port ${port} sur ${host}...`);

  const res = await api("/api/runtime/test-port", {
    host,
    port,
    protocol: "tcp"
  });

  if (res.ok) {
    svc.port_ok = true;
    svc.latency_ms = res.latency_ms;
    toastSuccess(`Port OK (${res.latency_ms} ms)`);
  } else {
    svc.port_ok = false;
    toastError(`Port KO : ${res.error || "injoignable"}`);
  }

  persistState();
}

/* -----------------------------------------------------
   INIT
----------------------------------------------------- */
document.addEventListener("DOMContentLoaded", () => {
  loadMode().finally(() => {
    restoreState();
    hydrateFormFromState();

    if (state.domain?.dcs) {
      dcs = state.domain.dcs.slice();
      renderDCs();
    }

    if (state.services?.length > 0) {
      renderServiceAccounts();
      renderServicePorts();
    }

    const stepper = document.querySelector(".b2s-stepper");
    if (stepper) stepper.addEventListener("click", onStepperClick);

    showStep(currentStep || 1);
    updateJsonPreview();
  });
});
