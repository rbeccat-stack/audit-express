# PRD : Audit Growth Express — Frontend

**Version :** 1.1.0
**Date :** 2026-06-17

---

## 📌 Contexte

Page web minimaliste (style Lovable). Un recruteur tape l'URL d'une entreprise → reçoit en moins de 30s un audit growth streamé en temps réel. Lead magnet pour candidature.

**Infra :** FastAPI (port 8000) + Caddy reverse proxy → même domaine, CORS zéro.

---

## 🎯 Flux Utilisateur

1. Tape l'URL (ou nom) de l'entreprise
2. Optionnel : son email ("On t'envoie l'audit")
3. Clique "Auditer"
4. Spinner + progression live :
   - 🔍 Scraping du site...
   - 📰 Recherche actualités...
   - ⚡ Analyse en cours...
5. ✅ Résultat : Strength / Opportunity / Interview Question / Candidate Fit
6. 📋 Copy-to-clipboard

---

## 🏗️ Contrat Backend

```
GET /api/audit?url=spotify.com&email=recruiter@mail.com
→ SSE (Content-Type: text/event-stream)
```

**Query params**
- `url` (string, required) — URL de l'entreprise
- `email` (string, optional) — email du recruteur pour suivi

**Events**
- `progress` → message textuel
- `result` → JSON `{entreprise, force_detectee, opportunity_growth, question_entretien, candidat_fit, temps_generation}`
- `error` → message d'erreur

---

## 💻 Composants Front

- **Layout** : 600px max-width, mobile-first
- **Input zone** : URL input + email input (optionnel) + bouton Auditer
- **Status zone** : spinner + message dynamique (caché au start)
- **Result zone** : 4 sections + timing + copy button (caché au start)
- **Error zone** : message + bouton Retry (caché au start)

---

## 🔧 JS Logic

- `EventSource` natif (pas de fetch + ReadableStream)
- Construction de l'URL : `` `/api/audit?url=${encodeURIComponent(url)}&email=${encodeURIComponent(email)}` ``
- **Timeout 45s critique** : si ni `result` ni `error` n'est reçu dans ce délai, fermer l'EventSource et afficher une erreur ("ça prend trop de temps, réessaie")
- Sur `error` : fermer explicitement l'EventSource (`evtSource.close()`) pour tuer la reconnexion auto native
- Sur `result` : `JSON.parse` dans un `try/catch` (afficher une erreur de parsing plutôt que de crasher)
- Copy-to-clipboard sur l'audit complet (texte formaté, pas le JSON brut)

```js
const evtSource = new EventSource(apiUrl)
let timeoutId = setTimeout(() => {
  evtSource.close()
  showError("Ça prend trop de temps — réessaie.")
}, 45000)

evtSource.addEventListener('progress', (e) => {
  updateStatus(e.data)
})

evtSource.addEventListener('result', (e) => {
  clearTimeout(timeoutId)
  try {
    const audit = JSON.parse(e.data)
    displayAudit(audit)
  } catch (err) {
    showError("Erreur de lecture du résultat — réessaie")
  }
  evtSource.close()
})

evtSource.addEventListener('error', (e) => {
  clearTimeout(timeoutId)
  evtSource.close() // tue la reconnexion auto
  showError("Audit interrompu — réessaie")
})
```

---

## 🎨 Design

Deux univers visuels distincts, volontairement séparés selon la zone de l'interface.

### Zone hero + input — langage Lovable

- **Background** : gradient mesh flouté multi-couches (blanc → bleu pâle → rose/magenta), `radial-gradient` superposés + `filter: blur()`, statique (pas d'animation nécessaire)
- **Input** : pilule arrondie (`border-radius: 999px`), `backdrop-filter: blur(12px)`, fond semi-transparent blanc (`rgba(255,255,255,0.7)`), ombre douce
- **Bouton "Auditer"** : cercle plein, couleur d'accent `#2563eb` (cohérence avec la marque Hermes), icône flèche
- **Titre** : sans-serif bold arrondie, 24-28px, centré (ex : "Audite une boîte avant ton entretien")
- **Champ email** : sous l'input principal, même traitement glassmorphism, plus discret

### Zone résultat — langage Hermes Agent

- 4 cards bordées nettes : `border: 1px solid #e2e8f0`, `border-radius: 12px`, fond blanc — **pas** de glassmorphism ici, contraste volontaire avec le hero
- Label de chaque card en majuscules, police mono légère, 11-12px, avec badge couleur :

| Section | Couleur badge |
|---|---|
| Force détectée | Vert |
| Opportunity growth | Bleu |
| Question entretien | Orange/ambre |
| Candidat fit | Rose/violet |

- **Timing** (`temps_generation`) : petit texte discret en bas, gris clair, mono, aligné à droite
- **Copy-to-clipboard** : icône seule, pas de bouton texte
- **Status zone (progress)** : spinner + texte simple, traitement épuré côté Lovable (état transitoire, pas un dashboard)

### Layout global

600px max-width, mono-écran, pas de sidebar/nav — seul le vocabulaire visuel (cards, badges, typo) d'Hermes est repris, pas sa structure de navigation.

---

## 📦 Stack

Plain HTML + Vanilla JS (ou Alpine.js si besoin de réactivité) — single HTML file, pas de build.

---

## ✅ Checklist

- [ ] Input URL + email
- [ ] Bouton Auditer (désactivé si URL vide)
- [ ] Status zone + spinner
- [ ] EventSource + timeout 45s
- [ ] Progress / Result / Error event handling
- [ ] Copy-to-clipboard
- [ ] Styling hero (Lovable) + résultat (Hermes), séparés comme décrit ci-dessus
- [ ] Mobile responsive
