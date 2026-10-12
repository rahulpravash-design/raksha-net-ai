# Front-end design system and 3D layer

Scope: the control centre (`apps/control-center`). The citizen and responder
apps keep their existing look; they share the notification bell, the recovery forms,
the form primitives (`Button`, `Field`, `TextInput`, …) and the account-security panels
(password change, two-factor enrolment) through `packages/ui`. Each app's
`components/ui.tsx` is now only a re-export of the shared primitives.

## 1. What exists

| Piece | Where | Notes |
|---|---|---|
| Dark "mission control" theme | `app/globals.css` | Tokens `--background #050914`, `--surface #0e192a`, accent cyan `#00e5ff`, priority colours in `lib/theme.ts`. `dark:` variants are keyed to a `dark` class on `<html>`, always set. |
| Landing page | `app/(landing)/page.tsx`, `components/landing/`, `lib/landing.ts` | Cinematic globe, the specified copy, two buttons that lead to real routes (`/dashboard`; the citizen app's `/report` via `NEXT_PUBLIC_CITIZEN_APP_URL`), then a platform section. The globe shows **live incidents to a signed-in dispatch-side user** (same endpoints as the dashboard, refreshed every 15 s, chips naming the real reference/category/priority, never report text) and **labelled demonstration markers to everyone else** (`globeMode`). The platform section has one card per screen that exists (`platformFeatures.ts`; a test proves every link has a page) and shows each viewer a link, a sign-in prompt, or "Not available to your role". On narrow screens the globe is its own block above the list; on wide screens it sits behind the copy. |
| Globe | `components/3d/` | React Three Fiber scene: land from real Natural Earth data, graticule, atmosphere shader, **glowing priority markers** (a soft disc of the band colour lying on the surface, breathing slowly; steady under reduced motion; `glowTexture.ts`), a slow ring for critical or selected markers, great-circle arcs (demonstration only), drag to rotate, pointer parallax. Lazy-loaded; WebGL check; error boundary; static SVG fallback. |
| Command centre | `app/(console)/dashboard/page.tsx`, `components/command-center/` | Sidebar, connection/freshness strip, priority tiles, Map ⇄ Globe switch, selected-incident panel, activity timeline, animated queue. |
| Operational map | `components/IncidentMap.tsx`, `components/maps/` | Leaflet + OSM tiles. Grid clustering (`lib/cluster.ts`), per-priority marker shapes, resource layer, legend, selected-incident pulse. |
| Motion | `components/animations/` | `MotionConfig reducedMotion="user"` once, shared timing; `Reveal` entrance. |
| Notification inbox | `packages/ui` | Bell, unread badge, panel; used in all three apps. |
| Incident detail | `app/(console)/incidents/[id]`, `components/incident/` | Header with key-fact chips (urgent facts in words + glyph), collapsible panels (`aria-expanded`), status timeline marking the current state, skeleton loader, error state with retry. Move/override actions extracted to `IncidentActions`. |
| Incident quick-view drawer | `components/command-center/IncidentDrawer.tsx` | Modal slide-over from the dashboard: focus moves in, Escape/backdrop closes, focus returns to the opener. |
| Hospitals | `app/(console)/hospitals`, `components/hospitals/` | Capacity cards (beds/ICU in words, accepting status, how old the report is — flagged after 6 h, a display convention), detail, capacity report form (only changes sent), inbound-patient notices with role-appropriate actions. A hospital operator lands here and sees only hospitals and their own inbound notices. |
| Hospital notice from an incident | `components/hospitals/HospitalNoticePanel.tsx`, `NotifyHospital.tsx` | Notices for the incident; dispatchers pick a nearby hospital with free beds, fill count/ETA/severity/clinical notes, review what will and will not travel, then send. |
| Accounts (admin) | `app/(console)/admin/users`, `components/admin/` | Search/filter/paginate accounts; see role, active, 2FA and lockout state; create an account (generated or typed initial password, shown once; the person must replace it at first sign-in); set a temporary password for someone who forgot theirs (shown once; ends their sessions, clears any lockout); edit profile; change role and deactivate/reactivate (confirmations); unlock; reset a lost second factor (confirmation). Hides what the server refuses: no self role/active change or self MFA reset; a plain administrator cannot manage or grant super administrator. |
| Hospital registration | `components/hospitals/HospitalRegisterForm.tsx` | Administrators register a hospital and pick its operator from active hospital-operator accounts. |
| Crew picker | `components/resources/ResourceForm.tsx` | Dispatchers link a responder to a unit via `/users/directory` (no email, phone or other roles). |
| Account security | `app/(console)/account/security`, `components/PasswordSettings.tsx`, `MfaSettings.tsx`, `QrCode.tsx` | Change your own password (current + new + repeat, plus an authenticator code when 2FA is on; the server's message is shown for weak passwords; other sessions are signed out). An account whose password an administrator set is sent here at sign-in and by the API client's `onPasswordChangeRequired` hook, with a banner, until it is replaced. Two-factor enrolment for the signed-in user: QR code (drawn as an SVG path from the `qrcode` module matrix — no HTML injection) plus a typeable setup key, confirm with a code, turn off with password + code. Under `RAKSHA_MFA_REQUIRED_FOR_OPERATIONAL` the API client's `onMfaEnrolmentRequired` hook sends an unenrolled user here instead of showing failed requests. |
| Analytics | `app/(console)/analytics`, `components/analytics/`, `lib/analytics.ts` | Dispatch roles only. Period presets (24 h / 7 d / 30 d / all time) and a category filter; median-led time-to-dispatch and time-to-resolution cards that always show the sample size, flag fewer than 5 cases as anecdotal and say "nothing to measure" instead of 0; category and resource-use bars (one hue, values printed on every row, so the list reads as a table); hotspots as ranked grid cells showing coarsened centres only. Plain CSS bars — no chart library, no categorical palette, so the palette validator had nothing to validate. |
| Password recovery | `packages/ui/src/RecoveryForms.tsx`; `forgot-password` and `reset-password` pages in all three apps; "Forgot your password?" on each sign-in | Asks the API whether email recovery exists and, if not, says to ask an administrator instead of promising a message. After a request it gives one non-committal answer for every address. The reset page reads the token from the link and removes it from the address bar, offers mismatch/weak-password feedback without spending the link, and shows "Link not valid" with a way to request a new one. |
| Resource inventory | `app/(console)/resources`, `components/resources/` | Stats from `/resources/stats/summary`, search + type/status filters + pagination, cards, detail panel, register/edit forms, availability and deactivate controls. |

## 2. Rules the visuals follow

* **The globe is decoration; the map is operational.** The globe never carries
  routing or distance meaning. Operational geography stays on the Leaflet map and
  in the backend.
* **No fabricated data, and no real locations for visitors.** The landing page is
  public. An anonymous visitor, a citizen, a responder or a hospital operator sees
  only real city coordinates with *illustrative* priorities, labelled
  "Demonstration markers — not live incidents" in the page itself
  (`components/landing/demoData.ts`) — real emergency locations never go to a
  viewer the API would refuse them to (CLAUDE.md section 5). A signed-in
  dispatcher, admin or super admin sees the platform's real open incidents; the
  count is the API's own `total_open`, the globe says when it draws fewer than that,
  no arcs are drawn between real incidents (that would be an invented relationship),
  an empty queue says "No open incidents right now", and an unreachable feed says so
  and shows nothing — never the demonstration markers. While the session is being
  read nothing is drawn, so demo markers cannot flash up in front of an operator.
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
| `qrcode` (+ `@types/qrcode`) | The MFA enrolment QR (now a dependency of `packages/ui`, shared by all three apps). Authenticator apps are normally enrolled by scanning; the setup key is shown too as a fallback. Used only for its module matrix. | Small; loaded with the security page. |
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
* **Passwords:** changing your own password, the forced change for administrator-set
  passwords, the administrator's temporary-password reset and (when an SMTP host is
  configured) recovery by email all exist. Without an SMTP host a forgotten password needs
  an administrator, and an administrator who forgets theirs needs another administrator.
  The responder app's recovery pages share the same components but were not driven in a
  browser; the control centre and citizen app were.
* **MFA has no recovery codes** (the backend has none). A user who loses the device
  needs an administrator to reset it, and an administrator cannot reset their own.
  The enrolment screen says this before the user relies on it. A user can also turn
  MFA off while policy requires it; the next request then sends them back to enrol.
* **Analytics limits:** no time-series or trend lines (the API returns aggregates only),
  no map of hotspots (cells are listed), no export, and the category filter applies
  only to the time measures and hotspots because that is all the API supports. The
  "fewer than 5 cases" threshold is a display convention, not a statistical test.
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
* `landing-live.mjs` — a visitor sees demonstration markers and the page makes no incident request and shows no real reference code; a dispatcher's count equals the API's open total, the chips are the API's top eight in order, a chip offers that incident's page (never its text), a new report raises the count within the refresh window without a reload; a hospital operator keeps demonstration data with the reason and no incident request; phone width, reduced motion and WebGL-off all work (29 checks).
* `csp.mjs` — all three apps: a fresh nonce on every request, no `'unsafe-inline'` or (in production) `'unsafe-eval'` in `script-src`, every rendered script carrying the nonce; the apps hydrate and answer a sign-in; a `<script>` injected into the served HTML and an `onerror=` handler injected after load do not run and the browser reports refusing them; the 3D landing renders with no violations.
* `mfa-recovery.mjs` — an administrator turns two-factor on and is shown ten recovery codes (Done stays disabled until they are marked saved; the codes are gone from the page afterwards); with no device, a code typed loosely signs them in, the count drops to nine, the same code is refused a second time, the set is replaced (old unused codes stop working), and two-factor is turned off using only a recovery code — the lone-administrator case; the responder app signs a responder in with a recovery code; phone width.
* `hospital-edit.mjs` — an administrator edits a hospital's name, phone, address and position from the screen (server agrees; capacity untouched), relinks the operator (the previous one loses access), is refused retiring while a notice is open and shown the reason, retires once it is closed, restores it from the retired view; a dispatcher gets no button and a 403; phone width.
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
* `recovery.mjs` — two modes. `unavailable`: the page says recovery by email is not set up and offers no form. `mailbox`: against a real SMTP conversation with `scripts/dev_mailbox.py`, an unknown and a known address get the identical answer and only the known one gets mail; the link points at the configured app (control centre for a dispatcher, citizen app for a citizen); the token leaves the address bar; mismatch and weak passwords are refused without spending the link; a really locked account recovers; the old password stops working; a "password was changed" notice arrives with no secret in it; the link cannot be used twice; mobile overflow.
* `password.mjs` — an admin-created account is refused everything but the password change and lands on the security screen (even typing `/dashboard` bounces back); client and server refusals (mismatch, weak, wrong current password) leave the session intact; the forced change sends the user home and the console works; a voluntary change ends the other device's refresh token while this browser stays signed in; an administrator really locks an account, sets a generated temporary password (shown once, nothing changes before confirmation), and the user can then sign in with it, flagged to change it; no temporary password is offered for oneself; mobile overflow.
* `admin.mjs` — non-admins cannot reach Accounts (UI and API); a really-locked
  account is shown Locked and Unlock lets it sign in; MFA reset (needs confirmation,
  then sign-in without a code); role change; deactivate/reactivate (inactive login
  refused); own-row protections; create an operator and prove the shown password
  works; duplicate email refused; register a hospital linked to that operator who
  can then report capacity; crew picker links a responder; mobile overflow.
* `mfa.mjs` — enrolment with an independently computed TOTP: the QR is screenshotted
  and **decoded with OpenCV** to confirm it carries the setup key; a wrong code is
  refused; sign-in then asks for a code; turn-off needs the right password. Run again
  with `MFA_ENFORCED=1` against an API started with
  `RAKSHA_MFA_REQUIRED_FOR_OPERATIONAL=true` to prove an unenrolled operator is sent
  to the security screen and the console works after enrolling.
* `analytics.mjs` — builds one complete report→dispatch→resolved case, then checks the
  cards against the API's own figures (sample size, category total), that hotspots
  show cell centres and never the report's exact coordinates, period and category
  filters re-query, a hospital operator gets no link and is sent home (and the API
  refuses a responder), mobile overflow.
* `dispatch.mjs` — the dispatch workflow (see CHECKPOINT).
* `responder-scope.mjs` — a responder is refused every incident read by the API (queue,
  detail, history, media, analyses, dispatches, notices, recommendations, map feed) and
  cannot be made an incident's assignee, still reads their own assignments; the control
  centre keeps them on the login page with a pointer to the responder app and leaves no
  session; a dispatcher is unaffected.

Chromium ran WebGL through software rendering (SwiftShader). That proves the
scene initialises and draws; it says nothing about GPU performance.
