const API = "http://127.0.0.1:8000";

// ---------- 1. Identifier l'utilisateur et ouvrir une session ----------
async function ensureSession() {
  let user_id = localStorage.getItem("user_id");
  let session_id = sessionStorage.getItem("session_id");
  if (user_id && session_id) return { user_id: Number(user_id), session_id };

  const email = localStorage.getItem("email") || prompt("Ton email :");
  const res = await fetch(`${API}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  const data = await res.json();
  localStorage.setItem("email", email);
  localStorage.setItem("user_id", data.user_id);        // reste après fermeture du navigateur
  sessionStorage.setItem("session_id", data.session_id); // disparaît à la fermeture de l'onglet
  return data;
}

// ---------- 2. Envoyer un événement ----------
async function track(news_id, event_type) {
  const { user_id, session_id } = await ensureSession();
  await fetch(`${API}/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id, session_id, news_id, event_type }),
  });
  console.log("tracké :", event_type, news_id);
}

// ---------- 3. Petits outils d'affichage ----------
// Empêche un titre contenant "<" ou "&" de casser la page
function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// Une carte d'article (utilisée par les deux sections)
function renderCard(a) {
  return `
    <article class="card" data-id="${escapeHtml(a.id)}">
      <span class="cat">${escapeHtml(a.category)}</span>
      <h3 class="card-title">${escapeHtml(a.title)}</h3>
      <p class="card-abstract">${escapeHtml(a.abstract)}</p>
      <div class="card-actions">
        <button class="like" type="button">J'aime</button>
        <button class="share" type="button">Partager</button>
      </div>
    </article>`;
}

function renderMessage(text) {
  return `<p class="empty">${escapeHtml(text)}</p>`;
}

// ---------- 4. En-tête : date du jour + email ----------
function renderHeader() {
  const today = new Date().toLocaleDateString("fr-FR", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  });
  document.getElementById("today").textContent = today;
  const email = localStorage.getItem("email");
  document.getElementById("user-email").textContent = email ? `Connecté : ${email}` : "";
}

// ---------- 5. Afficher les articles "À la une" ----------
async function loadNews() {
  const list = document.getElementById("news-list");
  try {
    const res = await fetch(`${API}/news?limit=20`);
    const articles = await res.json();
    list.innerHTML = articles.length
      ? articles.map(renderCard).join("")
      : renderMessage("Aucun article pour le moment.");
  } catch {
    list.innerHTML = renderMessage("Impossible de charger les articles.");
  }
}

// ---------- 6. Afficher les recommandations ----------
async function loadRecommendations() {
  const list = document.getElementById("reco-list");
  try {
    const { user_id } = await ensureSession();
    const res = await fetch(`${API}/recommendations?user_id=${user_id}`);
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();

    // On accepte { strategy, items: [...] } ou directement un tableau
    const items = Array.isArray(data) ? data : (data.items || data.recommendations || []);
    if (data.strategy === "cold_start" || items.length === 0) {
      list.innerHTML = renderMessage("Interagis avec des articles pour recevoir des recommandations");
      return;
    }
    list.innerHTML = items.map(renderCard).join("");
  } catch {
    list.innerHTML = renderMessage("Les recommandations ne sont pas disponibles pour le moment.");
  }
}

// ---------- 7. Les écouteurs ----------
// Même écouteur délégué qu'avant, branché sur les deux listes
function handleCardClick(e) {
  const card = e.target.closest(".card");           // la carte cliquée
  if (!card) return;
  const id = card.dataset.id;
  if (e.target.classList.contains("like"))       track(id, "like").then(loadRecommendations);
  else if (e.target.classList.contains("share")) track(id, "share").then(loadRecommendations);
  else                                            track(id, "click");
}
document.getElementById("news-list").addEventListener("click", handleCardClick);
document.getElementById("reco-list").addEventListener("click", handleCardClick);

ensureSession().then(() => {
  renderHeader();
  loadRecommendations();
  loadNews();
});
