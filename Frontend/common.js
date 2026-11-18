// common.js : outils partagés par toutes les pages connectées
// (index.html, algorithms.html, interactions.html).
// À charger AVANT le script propre à chaque page.

const API = "http://127.0.0.1:8000";

// ---------- 1. Authentification ----------
// Déconnexion : on efface tout et on retourne à la page de connexion
function logout() {
  localStorage.clear();
  sessionStorage.clear();
  window.location.replace("login.html");
}

// fetch qui ajoute le jeton ; si le serveur répond 401 (jeton absent/expiré) → login
async function authFetch(url, options = {}) {
  const token = localStorage.getItem("token");
  if (!token) { logout(); throw new Error("no token"); }
  const res = await fetch(url, {
    ...options,
    headers: { ...(options.headers || {}), Authorization: `Bearer ${token}` },
  });
  if (res.status === 401) { logout(); throw new Error("401"); }
  return res;
}

// Vérifie le jeton auprès du serveur : { user_id, role, session_id }
async function fetchMe() {
  const res = await authFetch(`${API}/me`);
  if (!res.ok) throw new Error(res.status);
  const me = await res.json();
  localStorage.setItem("role", me.role);      // la vérité vient du serveur
  return me;
}

// Pages réservées à l'admin : sans jeton → login, rôle "user" → accueil.
// Ce n'est qu'un confort d'affichage : la vraie protection est le 403 du serveur.
async function requireAdmin() {
  if (!localStorage.getItem("token")) {
    window.location.replace("login.html");
    throw new Error("no token");
  }
  const me = await fetchMe();
  if (me.role !== "admin") {
    window.location.replace("index.html");
    throw new Error("forbidden");
  }
  return me;
}

// ---------- 2. Petits outils d'affichage ----------
// Empêche un titre contenant "<" ou "&" de casser la page
function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// Petit message temporaire en bas de l'écran (élément #toast)
function showToast(text) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = text;
  toast.classList.add("is-visible");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("is-visible"), 2600);
}

// En-tête commun : date du jour, email, année du footer, bouton de déconnexion,
// et affichage des éléments ".admin-only" si l'utilisateur est admin.
function renderHeader(me) {
  const today = new Date().toLocaleDateString("fr-FR", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  });
  document.getElementById("today").textContent = today;
  document.getElementById("user-email").textContent = localStorage.getItem("email") || "";
  document.getElementById("year").textContent = new Date().getFullYear();

  const isAdmin = Boolean(me && me.role === "admin");
  document.querySelectorAll(".admin-only").forEach(el => { el.hidden = !isAdmin; });
}

// ---------- 3. Pages admin : appel API avec repli sur des données factices ----------
// Tant que la route n'existe pas côté serveur (404), on lit un fichier JSON local
// et on affiche le bandeau "Données de démonstration".
// Renvoie { data, demo } où demo = true si les données sont factices.
async function fetchAdminData(path, mockFile) {
  const res = await authFetch(`${API}${path}`);
  if (res.ok) return { data: await res.json(), demo: false };
  if (res.status === 404) {
    const mock = await fetch(mockFile);
    if (!mock.ok) throw new Error("mock " + mock.status);
    const banner = document.getElementById("demo-banner");
    if (banner) banner.hidden = false;
    return { data: await mock.json(), demo: true };
  }
  if (res.status === 403) {                    // le serveur refuse : pas admin
    window.location.replace("index.html");
  }
  throw new Error(res.status);
}
