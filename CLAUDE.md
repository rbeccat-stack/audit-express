# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Audit Growth Express** — A single-page lead magnet web app. A recruiter enters a company URL → receives a streamed AI growth audit in under 30s.

## Stack

Plain HTML + Vanilla JS (no build step, no framework). Single `index.html` file. Alpine.js allowed if reactivity becomes unwieldy.

Backend: FastAPI on port 8000, fronted by Caddy reverse proxy on the same domain → zero CORS issues. Never add CORS headers or fetch workarounds; Caddy handles it.

## Backend Contract

```
GET /api/audit?url=<encoded_url>&email=<encoded_email>
Content-Type: text/event-stream
```

SSE events:
- `progress` → string message for status display
- `result` → JSON `{ entreprise, force_detectee, opportunity_growth, question_entretien, candidat_fit, temps_generation }`
- `error` → error string

## UI Behavior

- Bouton "Auditer" désactivé (`disabled`) tant que le champ URL est vide
- Zone erreur : affiche le message + un bouton **Retry** qui remet l'interface en état initial (masque result/status, réactive le bouton)
- Zone status (progress) : spinner + texte simple, traitement épuré style Lovable — c'est un état transitoire, pas un dashboard

## JS Rules

- Use native `EventSource`, not `fetch` + `ReadableStream`
- 45s hard timeout: if neither `result` nor `error` arrives, close the EventSource and show error
- On `error` event: always call `evtSource.close()` explicitly to prevent auto-reconnect
- On `result` event: wrap `JSON.parse` in `try/catch`
- Copy-to-clipboard copies formatted text, not raw JSON

## Design System

Two distinct visual languages, never mixed:

**Hero + input zone (Lovable style)**
- Background: static multi-layer blurred radial gradient mesh (white → pale blue → rose/magenta)
- Input: pill shape (`border-radius: 999px`), `backdrop-filter: blur(12px)`, semi-transparent white `rgba(255,255,255,0.7)`
- Audit button: filled circle, accent color `#2563eb`, arrow icon
- Email field: same glassmorphism treatment, more subdued

**Result zone (Hermes Agent style)**
- 4 cards: `border: 1px solid #e2e8f0`, `border-radius: 12px`, solid white background — no glassmorphism here, intentional contrast
- Card labels: uppercase, light mono font, 11-12px, with color badge:
  - Force détectée → green
  - Opportunity growth → blue
  - Question entretien → orange/amber
  - Candidat fit → rose/violet
- Timing (`temps_generation`): small grey mono text, right-aligned
- Copy button: icon only, no text label

**Layout**: 600px max-width, single screen, no nav/sidebar, mobile-first.
