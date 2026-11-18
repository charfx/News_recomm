// interactions.js : page admin « Interactions »
// Lit GET /admin/interactions et dessine les graphiques à la main (HTML + SVG, sans librairie).
// Dépend de common.js (API, authFetch, escapeHtml, requireAdmin, fetchAdminData...).

// Couleurs (mêmes valeurs que style.css)
const COLOR_POS = [20, 48, 92];      // bleu nuit  #14305c  → score positif
const COLOR_NEG = [168, 50, 43];     // rouge brique #a8322b → score négatif
const COLOR_MID = [236, 231, 220];   // neutre #ece7dc      → 0 (aucune interaction)
const NEUTRAL = "rgb(236,231,220)";

// Libellés français des types d'événements
const EVENT_LABELS = {
  click: "Clic", like: "J'aime", share: "Partage", dislike: "Je n'aime pas", skip: "Ignoré",
};

const fmt = n => Number(n).toLocaleString("fr-FR");

// ---------- 1. Infobulle partagée ----------
const tooltip = document.getElementById("tooltip");

function showTip(html, x, y) {
  tooltip.innerHTML = html;
  tooltip.classList.add("is-visible");
  // On place l'infobulle près de la souris sans sortir de l'écran
  const w = tooltip.offsetWidth, h = tooltip.offsetHeight;
  let left = x + 14, top = y + 14;
  if (left + w > window.innerWidth - 8) left = x - w - 14;
  if (top + h > window.innerHeight - 8) top = y - h - 14;
  tooltip.style.left = `${Math.max(8, left)}px`;
  tooltip.style.top = `${Math.max(8, top)}px`;
}

function hideTip() {
  tooltip.classList.remove("is-visible");
}

// Tout élément portant data-tip affiche son contenu au survol
document.addEventListener("mousemove", e => {
  const target = e.target.closest("[data-tip]");
  if (target) showTip(target.dataset.tip, e.clientX, e.clientY);
  else hideTip();
});

// ---------- 2. Chiffres clés ----------
function renderKpis(k) {
  const items = [
    [fmt(k.users), "Utilisateurs"],
    [fmt(k.items), "Articles"],
    [fmt(k.events), "Événements"],
    [`${(k.density * 100).toLocaleString("fr-FR", { maximumFractionDigits: 2 })} %`, "Densité de la matrice"],
  ];
  document.getElementById("kpis").innerHTML = items.map(([value, label]) => `
    <div class="kpi">
      <div class="kpi-value">${escapeHtml(value)}</div>
      <div class="kpi-label">${escapeHtml(label)}</div>
    </div>`).join("");
}

// ---------- 3. Barres horizontales (gère les valeurs négatives) ----------
// rows = [{ label, value, tip }]
function renderHBars(elementId, rows) {
  const el = document.getElementById(elementId);
  if (!rows.length) { el.innerHTML = `<li class="empty">Aucune donnée.</li>`; return; }

  const maxPos = Math.max(0, ...rows.map(r => r.value));
  const maxNeg = Math.max(0, ...rows.map(r => -r.value));
  const span = (maxPos + maxNeg) || 1;
  const axis = (maxNeg / span) * 100;          // position du zéro, en %

  el.innerHTML = rows.map(r => {
    const width = (Math.abs(r.value) / span) * 100;
    const neg = r.value < 0;
    const left = neg ? axis - width : axis;
    return `
      <li class="hbar" data-tip="${escapeHtml(r.tip)}">
        <span class="hbar-label">${escapeHtml(r.label)}</span>
        <span class="hbar-track">
          <span class="hbar-fill${neg ? " is-neg" : ""}" style="left:${left}%;width:${width}%"></span>
          ${maxNeg > 0 ? `<span class="hbar-axis" style="left:${axis}%"></span>` : ""}
        </span>
        <span class="hbar-value">${fmt(r.value)}</span>
      </li>`;
  }).join("");
}

// ---------- 4. Barres verticales par jour (SVG) ----------
// Arrondit le maximum de l'axe à une valeur « ronde » (10, 20, 50, 100...)
function niceMax(value) {
  if (value <= 0) return 1;
  const pow = 10 ** Math.floor(Math.log10(value));
  const n = value / pow;
  const nice = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
  return nice * pow;
}

function renderByDay(days) {
  const el = document.getElementById("by-day");
  if (!days.length) { el.innerHTML = `<p class="empty">Aucune donnée.</p>`; return; }

  // Dimensions du dessin (le SVG s'adapte ensuite à la largeur grâce au viewBox)
  const W = 600, H = 240, m = { top: 12, right: 8, bottom: 28, left: 36 };
  const plotW = W - m.left - m.right, plotH = H - m.top - m.bottom;
  const max = niceMax(Math.max(...days.map(d => d.count)));
  const step = plotW / days.length;
  const barW = Math.max(2, step - 4);               // 4 px d'écart entre les barres
  const y = v => m.top + plotH - (v / max) * plotH;
  const labelEvery = Math.ceil(days.length / 8);    // pas plus de ~8 dates sous l'axe

  // Grille horizontale : 4 graduations
  const ticks = [0, 0.25, 0.5, 0.75, 1].map(t => t * max);
  const grid = ticks.map(t => `
    <line x1="${m.left}" x2="${W - m.right}" y1="${y(t)}" y2="${y(t)}"></line>
    <text x="${m.left - 6}" y="${y(t) + 4}" text-anchor="end">${fmt(Math.round(t))}</text>`).join("");

  const bars = days.map((d, i) => {
    const x = m.left + i * step + (step - barW) / 2;
    const h = Math.max(0, m.top + plotH - y(d.count));
    const date = new Date(d.day + "T00:00:00");
    const short = date.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" });
    const long = date.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });
    const r = Math.min(4, barW / 2, h);             // bout arrondi de 4 px, base droite
    const top = m.top + plotH - h;
    const path = h > 0
      ? `M${x},${m.top + plotH} V${top + r} Q${x},${top} ${x + r},${top} H${x + barW - r} Q${x + barW},${top} ${x + barW},${top + r} V${m.top + plotH} Z`
      : "";
    const tip = `<strong>${escapeHtml(long)}</strong><br>${fmt(d.count)} événements`;
    return `
      <g class="day-col" data-tip="${escapeHtml(tip)}">
        <rect class="day-hit" x="${m.left + i * step}" y="${m.top}" width="${step}" height="${plotH}"></rect>
        ${path ? `<path class="day-bar" d="${path}"></path>` : ""}
        ${i % labelEvery === 0 ? `<text x="${x + barW / 2}" y="${H - 8}" text-anchor="middle">${short}</text>` : ""}
      </g>`;
  }).join("");

  el.innerHTML = `
    <svg class="chart-svg" viewBox="0 0 ${W} ${H}" role="img"
         aria-label="Nombre d'événements par jour, du ${escapeHtml(days[0].day)} au ${escapeHtml(days[days.length - 1].day)}">
      <g class="grid">${grid}</g>
      <line class="baseline" x1="${m.left}" x2="${W - m.right}" y1="${m.top + plotH}" y2="${m.top + plotH}"></line>
      ${bars}
    </svg>`;
}

// ---------- 5. Top 10 des articles ----------
function renderTopItems(items) {
  const el = document.getElementById("top-items");
  if (!items.length) { el.innerHTML = `<li class="empty">Aucune donnée.</li>`; return; }
  el.innerHTML = items.slice(0, 10).map(a => `
    <li>
      <span class="top-title">
        <span class="cat">${escapeHtml(a.category)}</span>
        ${escapeHtml(a.title)}
      </span>
      <span class="top-score">${fmt(a.score)}</span>
    </li>`).join("");
}

// ---------- 6. Matrice user × item (heatmap) ----------
// Mélange deux couleurs RVB : t = 0 → a, t = 1 → b
function mix(a, b, t) {
  return `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(",")})`;
}

// Couleur divergente : négatif rouge, 0 neutre, positif bleu.
// Racine carrée pour que les petites valeurs restent visibles.
function cellColor(value, maxAbs) {
  if (!value) return NEUTRAL;
  const t = Math.sqrt(Math.min(1, Math.abs(value) / maxAbs));
  return mix(COLOR_MID, value > 0 ? COLOR_POS : COLOR_NEG, t);
}

function renderMatrix(matrix) {
  const el = document.getElementById("matrix");
  const users = matrix.users || [], items = matrix.items || [], values = matrix.values || [];
  if (!users.length || !items.length) { el.innerHTML = `<p class="empty">Aucune interaction.</p>`; return; }

  const maxAbs = Math.max(1, ...values.flat().map(v => Math.abs(v)));

  const head = items.map(it => `
    <th scope="col" title="${escapeHtml(it.title)}"><span>${escapeHtml(it.title)}</span></th>`).join("");

  const rows = users.map((u, r) => {
    const cells = items.map((it, c) => {
      const v = (values[r] && values[r][c]) || 0;
      const tip = `<strong>${escapeHtml(u.email)}</strong><br>${escapeHtml(it.title)}<br>Score : ${fmt(v)}`;
      return `<td style="background:${cellColor(v, maxAbs)}" data-tip="${escapeHtml(tip)}"
                  aria-label="${escapeHtml(`${u.email}, ${it.title} : ${v}`)}"></td>`;
    }).join("");
    return `<tr><th scope="row">${escapeHtml(u.email)}</th>${cells}</tr>`;
  }).join("");

  el.innerHTML = `
    <table class="matrix" aria-label="Score de chaque utilisateur pour chaque article">
      <thead><tr><td></td>${head}</tr></thead>
      <tbody>${rows}</tbody>
    </table>`;

  // Légende : rampe de couleurs de -max à +max
  document.getElementById("matrix-legend").innerHTML = `
    <span>${fmt(-maxAbs)}</span>
    <span class="ramp" style="background:linear-gradient(90deg, ${mix(COLOR_MID, COLOR_NEG, 1)}, ${NEUTRAL} 50%, ${mix(COLOR_MID, COLOR_POS, 1)})"></span>
    <span>+${fmt(maxAbs)}</span>
    <span>· rouge = désintérêt, neutre = aucune interaction, bleu = intérêt</span>`;
}

// ---------- 7. Assemblage ----------
function renderDashboard(data) {
  renderKpis(data.kpis || { users: 0, items: 0, events: 0, density: 0 });

  const total = (data.by_type || []).reduce((s, t) => s + t.count, 0) || 1;
  renderHBars("by-type", (data.by_type || []).map(t => ({
    label: EVENT_LABELS[t.event_type] || t.event_type,
    value: t.count,
    tip: `<strong>${escapeHtml(EVENT_LABELS[t.event_type] || t.event_type)}</strong><br>${fmt(t.count)} événements (${Math.round(t.count / total * 100)} %)`,
  })));

  renderByDay(data.by_day || []);
  renderTopItems(data.top_items || []);

  renderHBars("top-categories", (data.top_categories || []).map(c => ({
    label: c.category,
    value: c.score,
    tip: `<strong>${escapeHtml(c.category)}</strong><br>Score cumulé : ${fmt(c.score)}`,
  })));

  renderMatrix(data.matrix || {});
  document.getElementById("dashboard").setAttribute("aria-busy", "false");
}

function showLoadError(text) {
  document.getElementById("dashboard").hidden = true;
  const err = document.getElementById("load-error");
  err.textContent = text;
  err.hidden = false;
}

document.getElementById("logout").addEventListener("click", logout);

// ---------- 8. Démarrage ----------
requireAdmin()
  .then(async me => {
    renderHeader(me);
    try {
      const { data } = await fetchAdminData("/admin/interactions", "mock-interactions.json?v=1");
      renderDashboard(data);
    } catch {
      showLoadError("Impossible de charger les interactions. Vérifiez que l'API est démarrée, puis rechargez la page.");
    }
  })
  .catch(() => showLoadError("Le service est momentanément indisponible."));
