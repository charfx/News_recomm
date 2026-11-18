// API, logout(), authFetch(), fetchMe(), escapeHtml(), showToast(), renderHeader() : voir common.js
const algoSelect = document.getElementById("algo");
 
// Articles aimés pendant la session (pour garder l'état "Aimé" après un re-rendu)
const likedIds = new Set(JSON.parse(sessionStorage.getItem("liked") || "[]"));
 
// ---------- 2. Envoyer un événement ----------
// Plus de user_id / session_id : le serveur les lit dans le jeton
async function track(news_id, event_type) {
  await authFetch(`${API}/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ news_id, event_type }),
  });
}
 
// ---------- 3. Petits outils d'affichage ----------
// Libellés lisibles des stratégies renvoyées par l'API
const STRATEGY_LABELS = {
  popularity_ranker: "Tendances",
  cold_start: "Tendances",
  tfidf: "Selon vos lectures (TF-IDF)",
  embedding: "Selon vos lectures (sémantique)",
};
 
// Boutons J'aime / Partager (classes "like" et "share" : l'écouteur délégué en dépend)
function renderActions(a) {
  const liked = likedIds.has(String(a.id));
  return `
      <div class="card-actions">
        <button class="like${liked ? " is-active" : ""}" type="button" aria-pressed="${liked}">${liked ? "Aimé" : "J'aime"}</button>
        <button class="share" type="button">Partager</button>
      </div>`;
}
 
// Résumé facultatif : les recommandations n'ont pas toujours d'abstract
function renderAbstract(a) {
  return a.abstract ? `<p class="card-abstract">${escapeHtml(a.abstract)}</p>` : "";
}
 
// Carte "À la une" (variant = "hero" pour le premier article)
function renderCard(a, variant = "") {
  return `
    <article class="card${variant ? " card--" + variant : ""}" data-id="${escapeHtml(a.id)}">
      <span class="cat">${escapeHtml(a.category)}</span>
      <h3 class="card-title">${escapeHtml(a.title)}</h3>
      ${renderAbstract(a)}
      ${renderActions(a)}
    </article>`;
}
 
// Élément compact de la colonne "Pour vous"
function renderRecoItem(a, i) {
  return `
    <li class="reco-item">
      <article class="card card--reco" data-id="${escapeHtml(a.id)}">
        <span class="reco-num" aria-hidden="true">${i + 1}</span>
        <div class="reco-body">
          <span class="cat">${escapeHtml(a.category)}</span>
          <h3 class="card-title">${escapeHtml(a.title)}</h3>
          ${renderActions(a)}
        </div>
      </article>
    </li>`;
}
 
function renderMessage(text, tag = "p") {
  return `<${tag} class="empty">${escapeHtml(text)}</${tag}>`;
}
 
// ---------- 4. En-tête : renderHeader(me) est dans common.js ----------
 
// ---------- 5. Afficher les articles "À la une" ----------
async function loadNews() {
  const list = document.getElementById("news-list");
  try {
    const res = await authFetch(`${API}/news?limit=20`);
    if (!res.ok) throw new Error(res.status);
    const articles = await res.json();
    if (!articles.length) {
      list.innerHTML = renderMessage("Aucun article pour le moment.");
    } else {
      const [hero, ...rest] = articles;
      list.innerHTML =
        renderCard(hero, "hero") +
        `<div class="news-grid">${rest.map(a => renderCard(a)).join("")}</div>`;
    }
  } catch {
    list.innerHTML = renderMessage("Impossible de charger les articles. Vérifiez que l'API est démarrée, puis rechargez la page.");
  }
  list.setAttribute("aria-busy", "false");
}
 
// ---------- 6. Afficher les recommandations ----------
async function loadRecommendations({ fade = false } = {}) {
  const list = document.getElementById("reco-list");
  const badge = document.getElementById("reco-strategy");
  document.getElementById("reco-refresh").hidden = true;
  list.setAttribute("aria-busy", "true");
  if (fade) list.classList.add("is-fading");
 
  let html;
  try {
    // Plus de user_id dans l'URL : le serveur sait qui on est grâce au jeton
    const res = await authFetch(`${API}/recommendations`);
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    algoSelect.value = data.algorithm || "tfidf";
    badge.textContent = STRATEGY_LABELS[data.strategy] || data.strategy || "";
    badge.dataset.strategy = data.strategy || "";
 
    const items = Array.isArray(data) ? data : (data.items || data.recommendations || []);
    html = (data.strategy === "cold_start" || items.length === 0)
      ? renderMessage("Interagissez avec des articles pour recevoir des recommandations.", "li")
      : items.map(renderRecoItem).join("");
  } catch {
    badge.textContent = "";
    html = renderMessage("Les recommandations ne sont pas disponibles pour le moment.", "li");
  }
 
  if (fade) await new Promise(r => setTimeout(r, 200)); // laisse le fondu sortant se terminer
  list.innerHTML = html;
  list.setAttribute("aria-busy", "false");
  list.classList.remove("is-fading");
}
 
// Après un like / partage : on signale qu'une mise à jour est prête, sans remplacer la liste
function announceNewRecommendations() {
  document.getElementById("reco-refresh").hidden = false;
}
 
// ---------- 7. Les écouteurs ----------
function handleCardClick(e) {
  const card = e.target.closest(".card");
  if (!card) return;
  const id = card.dataset.id;
  const button = e.target.closest("button");
 
  if (button && button.classList.contains("like")) {
    if (likedIds.has(id)) return;
    markLiked(id);
    track(id, "like").then(announceNewRecommendations);
  } else if (button && button.classList.contains("share")) {
    track(id, "share").then(() => {
      showToast("Article partagé — merci !");
      announceNewRecommendations();
    });
  } else {
    track(id, "click");
  }
}
 
function markLiked(id) {
  likedIds.add(id);
  sessionStorage.setItem("liked", JSON.stringify([...likedIds]));
  document.querySelectorAll(`.card[data-id="${CSS.escape(id)}"] .like`).forEach(btn => {
    btn.classList.add("is-active");
    btn.setAttribute("aria-pressed", "true");
    btn.textContent = "Aimé";
  });
}
 
document.getElementById("news-list").addEventListener("click", handleCardClick);
document.getElementById("reco-list").addEventListener("click", handleCardClick);
document.getElementById("reco-refresh").addEventListener("click", () => loadRecommendations({ fade: true }));
document.getElementById("logout").addEventListener("click", logout);
 
algoSelect.addEventListener("change", async () => {
  const res = await authFetch(`${API}/admin/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ algorithm: algoSelect.value }),
  });
  showToast(res.ok ? "Algorithme appliqué à tous les utilisateurs" : "Changement refusé");
  loadRecommendations({ fade: true });
});
 
// ---------- 8. Démarrage ----------
// Sans jeton : on part tout de suite sur login.html, avant même d'afficher quoi que ce soit
if (!localStorage.getItem("token")) {
  window.location.replace("login.html");
} else {
  fetchMe().then(me => {
    renderHeader(me);
    loadRecommendations();
    loadNews();
  }).catch(() => {
    renderHeader(null);
    document.getElementById("news-list").innerHTML =
      renderMessage("Le service est momentanément indisponible. Vérifiez que l'API est démarrée, puis rechargez la page.");
    document.getElementById("news-list").setAttribute("aria-busy", "false");
    document.getElementById("reco-list").innerHTML =
      renderMessage("Les recommandations ne sont pas disponibles pour le moment.", "li");
    document.getElementById("reco-list").setAttribute("aria-busy", "false");
  });
}
 