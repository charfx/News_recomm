// login.js : seule page accessible sans jeton.
const API = "http://localhost:8000";
 
let mode = "login";                       // "login" | "register"
const form   = document.getElementById("auth-form");
const errBox = document.getElementById("auth-error");
const submit = document.getElementById("auth-submit");
 
// Déjà connecté avec un jeton valide ? On va directement aux articles.
(async () => {
  const token = localStorage.getItem("token");
  if (!token) return;
  const res = await fetch(`${API}/me`, { headers: { Authorization: `Bearer ${token}` } });
  if (res.ok) window.location.replace("index.html");
  else localStorage.clear();
})();
 
// Onglets Connexion / Inscription
document.querySelectorAll(".auth-tab").forEach(tab => {
  tab.addEventListener("click", () => {
    mode = tab.dataset.mode;
    document.querySelectorAll(".auth-tab").forEach(t => t.classList.toggle("active", t === tab));
    submit.textContent = mode === "login" ? "Se connecter" : "Créer mon compte";
    document.getElementById("password").autocomplete =
      mode === "login" ? "current-password" : "new-password";
    errBox.textContent = "";
  });
});
 
form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  errBox.textContent = "";
 
  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value;
  if (!email || password.length < 6) {
    errBox.textContent = "Email requis et mot de passe de 6 caractères minimum.";
    return;
  }
 
  submit.disabled = true;
  try {
    const res = await fetch(`${API}/${mode}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      errBox.textContent = data.detail || "Erreur de connexion.";
      return;
    }
    localStorage.setItem("token", data.token);
    localStorage.setItem("role", data.role);     // pour l'affichage seulement
    localStorage.setItem("email", data.email);
    window.location.replace("index.html");
  } catch {
    errBox.textContent = "Serveur injoignable.";
  } finally {
    submit.disabled = false;
  }
});
 