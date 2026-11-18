// algorithms.js : page admin « Algorithmes »
// Lit GET /admin/algorithms, affiche les algorithmes par famille,
// et permet d'en activer un avec PUT /admin/settings.
// Dépend de common.js (API, authFetch, escapeHtml, showToast, requireAdmin...).

let state = null;      // dernière réponse de /admin/algorithms
let demo = false;      // true si on affiche les données factices

// ---------- 1. Petits outils ----------
// Nombre de décimales à afficher selon le pas du curseur (0.05 → 2 décimales)
function decimalsOf(step) {
  const s = String(step ?? 1);
  return s.includes(".") ? s.split(".")[1].length : 0;
}

function formatValue(value, step) {
  return Number(value).toLocaleString("fr-FR", {
    minimumFractionDigits: decimalsOf(step),
    maximumFractionDigits: decimalsOf(step),
  });
}

// Valeur de départ d'un paramètre : celle de l'algo actif si c'est lui, sinon le défaut
function initialValue(algo, name, spec) {
  const active = state.active || {};
  if (active.algorithm === algo.id && active.params && active.params[name] !== undefined) {
    return active.params[name];
  }
  return spec.default;
}

// ---------- 2. Rendu d'une carte algorithme ----------
function renderParams(algo) {
  const entries = Object.entries(algo.parameters || {});
  if (!entries.length) return `<p class="params-none">Aucun paramètre réglable.</p>`;

  return entries.map(([name, spec]) => {
    const inputId = `p-${algo.id}-${name}`;
    const step = spec.step ?? (Number.isInteger(spec.default) ? 1 : 0.01);
    const value = initialValue(algo, name, spec);
    return `
      <div class="param">
        <div class="param-row">
          <label for="${escapeHtml(inputId)}">${escapeHtml(spec.label || name)}</label>
          <output class="param-value" for="${escapeHtml(inputId)}">${formatValue(value, step)}</output>
        </div>
        <input type="range" id="${escapeHtml(inputId)}" data-param="${escapeHtml(name)}"
               min="${spec.min}" max="${spec.max}" step="${step}" value="${value}"
               ${algo.available ? "" : "disabled"}>
        <div class="param-scale">
          <span>min ${formatValue(spec.min, step)}</span>
          <span>défaut ${formatValue(spec.default, step)}</span>
          <span>max ${formatValue(spec.max, step)}</span>
        </div>
        ${spec.help ? `<p class="param-help">${escapeHtml(spec.help)}</p>` : ""}
      </div>`;
  }).join("");
}

function renderList(items, tag, cls) {
  if (!items || !items.length) return `<p class="params-none">—</p>`;
  return `<${tag} class="${cls}">${items.map(t => `<li>${escapeHtml(t)}</li>`).join("")}</${tag}>`;
}

function renderAlgoCard(algo) {
  const isActive = state.active && state.active.algorithm === algo.id;
  const sources = algo.sources || [];
  let badge = "";
  if (isActive) badge = `<span class="badge badge--active">Actif</span>`;
  else if (!algo.available) badge = `<span class="badge badge--off">Non disponible</span>`;

  return `
    <article class="algo-card${isActive ? " is-active" : ""}" data-algo="${escapeHtml(algo.id)}">
      <div class="algo-card-head">
        <h3 class="card-title">${escapeHtml(algo.name)}</h3>
        ${badge}
      </div>
      <p class="algo-meta">Identifiant <code>${escapeHtml(algo.id)}</code> · version ${escapeHtml(algo.version || "—")}</p>
      <p class="algo-summary">${escapeHtml(algo.summary)}</p>

      <h4 class="algo-sub">Étapes</h4>
      ${renderList(algo.steps, "ol", "algo-steps")}

      <h4 class="algo-sub">Formule</h4>
      ${algo.formula ? `<pre class="formula">${escapeHtml(algo.formula)}</pre>` : `<p class="params-none">—</p>`}

      <h4 class="algo-sub">Limites</h4>
      ${renderList(algo.limitations, "ul", "algo-limits")}

      <h4 class="algo-sub">Paramètres</h4>
      ${renderParams(algo)}

      <div class="algo-actions">
        <button class="btn btn--primary js-activate" type="button"
                ${algo.available ? "" : "disabled"}>${isActive ? "Appliquer les réglages" : "Activer"}</button>
        ${sources.length ? `<button class="btn js-code" type="button" aria-expanded="false">Voir le code</button>` : ""}
      </div>
      <div class="code-viewer" hidden></div>
    </article>`;
}

// ---------- 3. Rendu des familles ----------
function renderFamilies() {
  const container = document.getElementById("families");
  const families = [...(state.families || [])];
  const algos = state.algorithms || [];

  // Un algorithme dont la famille n'est pas déclarée est rangé dans "Autres"
  const known = new Set(families.map(f => f.id));
  if (algos.some(a => !known.has(a.family))) {
    families.push({ id: "__other", name: "Autres", description: "" });
  }

  container.innerHTML = families.map(fam => {
    const members = algos.filter(a =>
      fam.id === "__other" ? !known.has(a.family) : a.family === fam.id);
    const titleId = `fam-${fam.id}`;
    return `
      <section class="family" aria-labelledby="${escapeHtml(titleId)}">
        <h2 id="${escapeHtml(titleId)}" class="section-title">${escapeHtml(fam.name)}</h2>
        ${fam.description ? `<p class="family-desc">${escapeHtml(fam.description)}</p>` : ""}
        ${members.length
          ? `<div class="algo-grid">${members.map(renderAlgoCard).join("")}</div>`
          : `<p class="family-empty">À implémenter.</p>`}
      </section>`;
  }).join("");
  container.setAttribute("aria-busy", "false");
}

// ---------- 4. Visionneuse de code ----------
// Chaque ligne est un <span> : les numéros sont ajoutés par le CSS (compteur)
function renderCode(content) {
  const lines = String(content ?? "").replace(/\n$/, "").split("\n");
  return lines.map(l => `<span class="code-line">${escapeHtml(l) || " "}</span>`).join("");
}

function showSource(card, index) {
  const algo = findAlgo(card.dataset.algo);
  const file = algo.sources[index];
  card.querySelectorAll(".code-tab").forEach((tab, i) => {
    tab.setAttribute("aria-selected", String(i === index));
  });
  card.querySelector(".code-block code").innerHTML = renderCode(file.content);
}

function toggleCode(card, button) {
  const viewer = card.querySelector(".code-viewer");
  const open = viewer.hidden;
  viewer.hidden = !open;
  button.setAttribute("aria-expanded", String(open));
  button.textContent = open ? "Masquer le code" : "Voir le code";

  // Construit la visionneuse au premier affichage seulement
  if (open && !viewer.dataset.ready) {
    const algo = findAlgo(card.dataset.algo);
    viewer.innerHTML = `
      <div class="code-tabs" role="tablist">
        ${algo.sources.map((s, i) => `
          <button class="code-tab" type="button" role="tab" data-index="${i}"
                  aria-selected="${i === 0}">${escapeHtml(s.path)}</button>`).join("")}
      </div>
      <pre class="code-block" tabindex="0"><code></code></pre>`;
    viewer.dataset.ready = "1";
    showSource(card, 0);
  }
}

// ---------- 5. Activation ----------
function findAlgo(id) {
  return (state.algorithms || []).find(a => a.id === id);
}

// Lit les curseurs de la carte : { lambda: 0.7, k: 10, ... }
function readParams(card) {
  const params = {};
  card.querySelectorAll("input[data-param]").forEach(input => {
    params[input.dataset.param] = Number(input.value);
  });
  return params;
}

async function activate(card, button) {
  const body = { algorithm: card.dataset.algo, params: readParams(card) };
  button.disabled = true;
  try {
    const res = await authFetch(`${API}/admin/settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (res.ok) {
      // Message affiché après le rechargement de la page
      sessionStorage.setItem("flash", "Algorithme activé");
      window.location.reload();
      return;
    }
    if (res.status === 404 && demo) {
      // Pas encore de backend : on simule l'activation sur la page
      state.active = body;
      renderFamilies();
      showToast("Algorithme activé (démonstration, non enregistré)");
      return;
    }
    showToast(res.status === 403 ? "Action réservée à l'administrateur." : "L'activation a échoué.");
  } catch {
    showToast("Serveur injoignable : l'algorithme n'a pas été activé.");
  }
  button.disabled = false;
}

// ---------- 6. Écouteurs (délégation sur le conteneur) ----------
const familiesEl = document.getElementById("families");

familiesEl.addEventListener("input", e => {
  const input = e.target.closest("input[data-param]");
  if (!input) return;
  const output = input.closest(".param").querySelector(".param-value");
  output.textContent = formatValue(input.value, input.step);
});

familiesEl.addEventListener("click", e => {
  const card = e.target.closest(".algo-card");
  if (!card) return;
  const codeBtn = e.target.closest(".js-code");
  const tab = e.target.closest(".code-tab");
  const activateBtn = e.target.closest(".js-activate");

  if (codeBtn) toggleCode(card, codeBtn);
  else if (tab) showSource(card, Number(tab.dataset.index));
  else if (activateBtn) activate(card, activateBtn);
});

document.getElementById("logout").addEventListener("click", logout);

// ---------- 7. Démarrage ----------
requireAdmin()
  .then(async me => {
    renderHeader(me);

    const flash = sessionStorage.getItem("flash");
    if (flash) { sessionStorage.removeItem("flash"); showToast(flash); }

    try {
      const result = await fetchAdminData("/admin/algorithms", "mock-algorithms.json?v=1");
      state = result.data;
      demo = result.demo;
      renderFamilies();
    } catch {
      familiesEl.innerHTML = `<p class="empty">Impossible de charger les algorithmes. Vérifiez que l'API est démarrée, puis rechargez la page.</p>`;
      familiesEl.setAttribute("aria-busy", "false");
    }
  })
  .catch(() => { /* redirection déjà lancée par requireAdmin (ou API injoignable) */
    familiesEl.innerHTML = `<p class="empty">Le service est momentanément indisponible.</p>`;
  });
