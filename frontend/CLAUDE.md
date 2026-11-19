# Amicorp portal-web (frontend)

The Angular app officers use: the Work Card portal and the UC1 validation workspace. The design is in
AMC-LLD-01, chapter "Portal Build (Angular)". The API is `../backend`.

## Layout rules

- `src/app/core/` holds singletons: auth (MSAL, roles, guards), config, the generated API client, SSE,
  the layout shell and error pages. `src/app/shared/` holds reusable UI, the theme and grid setup.
- `src/app/features/<name>/` holds one route area. Pages are default-exported standalone components
  named `*.page.ts`. Feature state is an NgRx SignalStore in that folder.
- Features do not import each other. Shared code goes in `shared/` or `core/`.
- Call the API only through `core/api/generated`. Regenerate it with `npm run api:gen`; never edit it.
  Until platform-api publishes the portal endpoints, use `core/api/portal-api.service.ts` and keep
  `docs/portal-api-contract.md` in step with `core/api/portal.models.ts`.
- Component selectors use the `amc-` prefix.
- Sign-in pages (`/login`, `/logout`, `/auth/callback`) live in `features/auth/`, outside the shell.
  Only `core/auth/auth.service.ts` calls MSAL; guards, pages and the account menu go through it.
- `public/udap/` is the UDAP landing page, which signed-out visitors to `/` see first. It is plain
  HTML, CSS and JS, not Angular, and the CSP applies: no inline `<style>`, `<script>` or `style=""`.
  After changing it, refresh the self-contained copy: `python -I ../udap-landing/make_standalone.py`.

## Design system

- Build pages from `shared/ui` (page header, chips, SLA, KPI tile, empty state, problem alert,
  avatar, skeleton, pipes) and the global classes in `shared/theme/_components.scss` (`amc-page`,
  `amc-panel*`, `amc-chip--*`, `amc-alert--*`, `amc-table`, `amc-dl`, `amc-cols-*`). Colours come
  from the tokens in `_tokens.scss`; never hard-code a new colour in a feature.
- Keep each component stylesheet under 4 kB (the budget); add shared styles globally instead.
- Show unavailable actions as disabled with the API's `ActionGate.reason` in a tooltip; do not
  re-implement business rules in the UI.
- Render times with the `amcTime` pipe (user's HK/EU zone) and money with `amcMoney`.
- The mock API (`core/mock/`, `mockApi: true`) must implement every endpoint the portal calls, with
  the same rules as the API; extend `mock-backend.spec.ts` when you add one.

## Enterprise UI rules

The portal must read like a business application, not a showcase.

- **Page header:** breadcrumbs, title, and at most a short factual subtitle (a team, a period, a
  count). No greetings, slogans, or sentences that explain how the system works.
- **Copy:** labels in sentence case. Helper text only where someone must decide something (a
  dialog or form field), one short sentence at most. Empty states: one line plus an optional link.
- **Decoration:** KPI tiles carry one tinted icon badge (`icon` input) and, where the API gives
  history, the change vs the previous period (`kpiTrend`) and a trend line (`spark`). No sparkle
  or "AI" icons and no coloured accent stripes; elsewhere icons appear only in navigation,
  buttons and status indicators.
- **Status:** work states use `amc-state-chip` (a dot and the name). Coloured tags (`amc-chip`)
  are only for severity, outcomes and version state.
- **Surfaces:** rounded cards (`amc-panel`, 10 px corners, soft shadow) on the light page
  background, Fluent-style; 6 px corners on buttons, fields and tags. No panel inside a panel.
- **Tables:** paginate any list that can grow beyond one page. AG Grids use `GRID_PAGING` from
  `shared/grid/ag-grid.setup.ts` (25 rows; 25/50/100). HTML tables use `paged()` and
  `<amc-paginator>` from `shared/ui/paginator.ts` (10 rows; 10/25/50). Short top-N lists on the
  overview end with a "View all" link instead.
- **Density:** 40 px table rows, 40 px form fields, 32 px buttons, 20–24 px page padding.
- **No tutorial panels** ("quick links", "your access", "how this works"). Roles and scope live in
  the account menu. Notes the docs require stay, each one muted line: the assistant's logging
  notice, and D-11 on screening evidence.

## Non-negotiables

- Route guards only shape the UI. The API enforces every rule, so never rely on a guard for security.
- Fail closed: if roles cannot be loaded, show nothing that needs a role.
- Sign-in is Entra ID only (MFA and conditional access apply there). The portal never asks for a
  password; the mock's account list stands in for Microsoft's account picker. Locally,
  `npm run start:api` lists the backend's sample officers instead (sign-in mode `local`,
  `core/auth/local-sign-in.ts`); the backend serves that sign-in only in local and test.
- No third-party origins at runtime (CSP `default-src 'self'`): self-host fonts and assets.
- AG Grid stays out of the initial bundle. Only lazy routes import `shared/grid`.
- Install with `npx -y npm@11 install` (npm 10.9 fails on this dependency tree).
