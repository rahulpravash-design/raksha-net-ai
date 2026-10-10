# Front-end design system and 3D layer

Scope: the control centre (`apps/control-center`). The citizen and responder
apps keep their existing look; they share only the notification bell
(`packages/ui`).

## 1. What exists

| Piece | Where | Notes |
|---|---|---|
| Dark "mission control" theme | `app/globals.css` | Tokens `--background #050914`, `--surface #0e192a`, accent cyan `#00e5ff`, priority colours in `lib/theme.ts`. `dark:` variants are keyed to a `dark` class on `<html>`, always set. |
| Landing page | `app/(landing)/page.tsx`, `components/landing/` | Cinematic globe, the specified copy, two buttons that lead to real routes (`/dashboard`; the citizen app's `/report` via `NEXT_PUBLIC_CITIZEN_APP_URL`). |
| Globe | `components/3d/` | React Three Fiber scene: land from real Natural Earth data, graticule, atmosphere shader, markers, great-circle arcs, drag to rotate, pointer parallax. Lazy-loaded; WebGL check; error boundary; static SVG fallback. |
| Command centre | `app/(console)/dashboard/page.tsx`, `components/command-center/` | Sidebar, connection/freshness strip, priority tiles, Map ⇄ Globe switch, selected-incident panel, activity timeline, animated queue. |
| Operational map | `components/IncidentMap.tsx`, `components/maps/` | Leaflet + OSM tiles. Grid clustering (`lib/cluster.ts`), per-priority marker shapes, resource layer, legend, selected-incident pulse. |
| Motion | `components/animations/` | `MotionConfig reducedMotion="user"` once, shared timing; `Reveal` entrance. |
| Notification inbox | `packages/ui` | Bell, unread badge, panel; used in all three apps. |
| Incident detail | `app/(console)/incidents/[id]`, `components/incident/` | Header with key-fact chips (urgent facts in words + glyph), collapsible panels (`aria-expanded`), status timeline marking the current state, skeleton loader, error state with retry. Move/override actions extracted to `IncidentActions`. |
| Incident quick-view drawer | `components/command-center/IncidentDrawer.tsx` | Modal slide-over from the dashboard: focus moves in, Escape/backdrop closes, focus returns to the opener. |
| Hospitals | `app/(console)/hospitals`, `components/hospitals/` | Capacity cards (beds/ICU in words, accepting status, how old the report is — flagged after 6 h, a display convention), detail, capacity report form (only changes sent), inbound-patient notices with role-appropriate actions. A hospital operator lands here and sees only hospitals and their own inbound notices. |
| Hospital notice from an incident | `components/hospitals/HospitalNoticePanel.tsx`, `NotifyHospital.tsx` | Notices for the incident; dispatchers pick a nearby hospital with free beds, fill count/ETA/severity/clinical notes, review what will and will not travel, then send. |
| Accounts (admin) | `app/(console)/admin/users`, `components/admin/` | Search/filter/paginate accounts; see role, active, 2FA and lockout state; create an account (generated or typed initial password, shown once); edit profile; change role and deactivate/reactivate (confirmations); unlock; reset a lost second factor (confirmation). Hides what the server refuses: no self role/active change or self MFA reset; a plain administrator cannot manage or grant super administrator. |
| Hospital registration | `components/hospitals/HospitalRegisterForm.tsx` | Administrators register a hospital and pick its operator from active hospital-operator accounts. |
| Crew picker | `components/resources/ResourceForm.tsx` | Dispatchers link a responder to a unit via `/users/directory` (no email, phone or other roles). |
| Resource inventory | `app/(console)/resources`, `components/resources/` | Stats from `/resources/stats/summary`, search + type/status filters + pagination, cards, detail panel, register/edit forms, availability and deactivate controls. |

## 2. Rules the visuals follow

* **The globe is decoration; the map is operational.** The globe never carries
  routing or distance meaning. Operational geography stays on the Leaflet map and
  in the backend.
* **No fabricated data.** The landing page is public and has no session, so its
  markers are real city coordinates with *illustrative* priorities, labelled
  "Demonstration markers — not live incidents" in the page itself
  (`components/landing/demoData.ts`). Signed-in views draw real incidents.
* **Priority is never colour alone.** Each band has a silhouette (triangle,
  diamond, square, circle), a word and a colour. Map markers carry a `title`/`alt`.
* **AI stays visibly separate.** The selected-incident panel labels the AI
  proposal "not verified", shows model name/version and review state, and has no
  dispatch control. Dispatch remains in the incident console, behind a confirmation.
* **Motion is restrained.** One slow ring on critical/selected markers (no
  flashing); entrance animations under 400 ms; no animation under
  `prefers-reduced-motion` (rotation, rings, grid drift, arc lights all stop).

## 3. Dependencies added (control centre) and why

| Package | Why | Cost |
|---|---|---|
| `three`, `@react-three/fiber` | The 3D scene. | Loaded only on the landing page and the Globe tab (dynamic import). |
| `motion` | Entrance, layout and reduced-motion handling in one place. | ~tens of KB. |
| `world-atlas` (data), `topojson-client` | Real coastlines for the globe instead of an invented planet. 55 KB Natural Earth 1:110m, public domain. | Part of the lazy chunk. |
| `@types/three`, `@types/topojson-client` (dev) | Types. | — |

`@react-three/drei` was deliberately not added: drag rotation, parallax and DOM
overlays are small enough to write directly.

## 4. Not done (from the original design brief)

Stated plainly, so this is not mistaken for a finished redesign:

* The **AI analysis panel** was not given the processing-step animation. The
  backend runs analysis synchronously, so there are no intermediate steps to show
  truthfully; adding them would be simulation.
* **Resource screen limits:** no "current assignment" (no per-resource dispatch endpoint), and manual
  availability is limited to Available / Out of service because committed states
  follow the dispatch. The backend itself would accept any status on that
  endpoint; the UI deliberately does not offer it.
* **No password change anywhere.** The API has no change-password or
  force-change-on-first-login endpoint, so an account's password is whatever the
  administrator set. The create form says so. This is the most important thing to
  build before real operators are onboarded.
* Accounts: no email change, no audit-log viewer, no bulk actions.
* Incident detail has no inline map and no attachment lightbox.
* **Responder and hospital apps** have no new visual identity; there is no
  hospital app.
* **Hospitals on the operational map** and **geographic search**: hospitals have a
  screen but no map layer; there is no geocoder.
* **Hospital screen limits:** administrators can register a hospital but not edit one
  afterwards (the API has no hospital edit endpoint, so the operator link cannot be
  changed); notices are not linked to a specific dispatch (the API supports it; the form does
  not ask); no map of hospital positions.
* **Who may act on a notice:** the receiving hospital acknowledges, confirms
  arrival or diverts (a reason is required); the dispatch side may only withdraw.
  The API would let a dispatcher mark a notice acknowledged on the hospital's
  behalf; the UI deliberately does not offer it.
* **Route visualisation** is absent because no route data exists (ETA is a
  straight-line estimate).
* **Performance** was not profiled beyond a headless software-rendered run
  (see §5). No frame-rate figures exist; do not quote any.
* OpenStreetMap tiles are not reachable from the build sandbox, so the map's
  base layer was never seen rendered with real tiles here — only markers on a
  blank background.

## 5. Verification actually run

`scripts/e2e/*.mjs` (need a running stack and `playwright-core`; not in the gate):

* `landing.mjs` — desktop, mobile (390 px), reduced motion, and WebGL disabled:
  canvas present or fallback shown, heading present, links correct, no horizontal
  overflow, no CSP/console errors.
* `command.mjs` — sign in, markers labelled, select an incident, panel contents,
  timeline, resource layer toggle, Map ⇄ Globe, inbox opens, markers focusable,
  mobile overflow, reduced-motion animations stopped.
* `bell.mjs` — a real dispatch raises the responder's unread count; the responder
  app's bell lists it, opens it, the server-side count drops; another user's
  attempt to mark it read is a 404.
* `resources.mjs` — inventory (register, validation, duplicate call sign, set out
  of service, filters, edit, two-step deactivate, role limits), the quick-view
  drawer (focus in/out, Escape), incident-detail header/collapsibles, and that
  the extracted status move still records history with its note; mobile overflow.
* `hospitals.mjs` — capacity report (validation, server state), notify from an
  incident (nothing sent before confirmation; payload has no reporter/text/location),
  hospital-operator sign-in lands on /hospitals with no incident or resource nav,
  /dashboard bounces back, their notices show ETA and clinical notes but never the
  report text or reporter, divert needs a reason, API refuses them incident reads,
  dispatcher sees the acknowledgement and withdraws; mobile overflow.
* `admin.mjs` — non-admins cannot reach Accounts (UI and API); a really-locked
  account is shown Locked and Unlock lets it sign in; MFA reset (needs confirmation,
  then sign-in without a code); role change; deactivate/reactivate (inactive login
  refused); own-row protections; create an operator and prove the shown password
  works; duplicate email refused; register a hospital linked to that operator who
  can then report capacity; crew picker links a responder; mobile overflow.
* `dispatch.mjs` — the dispatch workflow (see CHECKPOINT).

Chromium ran WebGL through software rendering (SwiftShader). That proves the
scene initialises and draws; it says nothing about GPU performance.
