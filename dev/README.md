# Local development

Everything runs on your laptop: PostgreSQL and Redis in Docker, the Platform API with Python, and your
own n8n. Nothing here is used in DEV, NPR or PRD.

```
 n8n  (localhost:5678) ── Bearer dev token ──►  platform-api  (127.0.0.1:8000)
   ▲                                              │
   └──────── webhook callbacks ◄──────────────────┤
                                                  ▼
                       Docker:  postgres:16 (127.0.0.1:5440)   redis:7 (127.0.0.1:6379)
```

## 1. Start PostgreSQL and Redis

From the repository root (`D:\Amicorp-AI`), not from `backend`:

```powershell
docker compose -f dev/docker-compose.yml up -d
```

## 2. Run the Platform API

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"        # first time, and after dependency changes
copy .env.example .env         # first time only; then set the tokens (see the comments in the file)
alembic upgrade head           # create or update the database tables
python -m scripts.seed         # sample officers, EN numbers, banks, rulesets; safe to run again
python -m app                  # http://127.0.0.1:8000, docs at /docs
```

`python -m app` uses the event loop psycopg needs on Windows. With plain `uvicorn`, add
`--loop asyncio:SelectorEventLoop`.

Use `127.0.0.1` rather than `localhost` in URLs: on Windows, `localhost` tries IPv6 first and stalls for
several seconds before falling back.

If the API stops at start-up with `ImportError: DLL load failed while importing _cache_key_cy: An Application
Control policy has blocked this file`, Windows Smart App Control is blocking SQLAlchemy's compiled speed-ups.
Install SQLAlchemy's pure-Python build of the same version instead (same behaviour, slightly slower). Repeat
this after anything reinstalls SQLAlchemy:

```powershell
$v = (pip show sqlalchemy | Select-String '^Version: (.+)').Matches.Groups[1].Value
pip download "sqlalchemy==$v" --no-deps --only-binary=:all: --platform any --python-version 3.12 -d "$env:TEMP\wheels"
pip install --force-reinstall --no-deps "$env:TEMP\wheels\sqlalchemy-$v-py3-none-any.whl"
```

Tests: `pytest` (the integration tests need step 1; they use a separate `amicorp_test` database).

## 3. Connect your n8n

n8n Community Edition has no Variables feature, so the workflows' `$vars.X` cannot work locally. The setup
script makes local copies that read `$env.X` instead, and binds the credentials. Your files in
`n8n-workflows/` are not changed.

1. Stop n8n (Ctrl+C in its window).
2. `.\dev\n8n\setup-n8n-local.ps1`. Run it once now, and again whenever a workflow file changes. It updates
   the existing workflows in place (same IDs) and adds the error handler as `AmiErrHandler001`.
3. `.\dev\n8n\start-n8n-local.ps1`. Always start n8n this way locally; it sets the `$env` values.

The setup writes `dev/n8n/out/`, which holds local tokens in plain text. It is git-ignored; do not share it.

The API credential uses `AUTOMATION_DEV_TOKEN` from `backend/.env`. If you change that token, run the setup
again. The API accepts the token only when `ENVIRONMENT` is `local` or `test`; DEV, NPR and PRD use Entra ID.

The extraction service calls n8n back on its webhook, so `backend/.env` also needs
`N8N_EXTRACTION_WEBHOOK_TOKEN`: the `extraction` value in `dev/n8n/out/local-secrets.json`.

To run UC1, activate it once (`n8n publish:workflow --id=vPwRzUT00rVmHcz6` while n8n is stopped), start n8n,
then send a statement the way the intake system would:

```powershell
$token = (Get-Content dev\n8n\out\local-secrets.json | ConvertFrom-Json).intake
Invoke-RestMethod -Method Post http://127.0.0.1:5678/webhook/bank-statement-received `
  -Headers @{ "X-Webhook-Token" = $token } -ContentType "application/json" `
  -Body '{"channel":"email","objectKey":"raw-docs/uc1/2026/10/hsbc-848-838.pdf","receivedAt":"2026-10-28T03:00:00Z"}'
```

A few seconds later the validation card waits in the Operations inbox. Every statement extracts to the same
12-line HSBC sample (the local extractor), with fields for the Maker to correct.

### UC2, UC3 and the stuck-item sweeper

Activate each once, the same way, while n8n is stopped:

```powershell
n8n publish:workflow --id=DtzF1bAiEVG1FokV   # UC2 Transaction monitoring (AML)
n8n publish:workflow --id=1F66HcgBhqJULu2Z   # UC3 NAV statement validation
n8n publish:workflow --id=rwIQ665J6hDgTXYq   # Platform stuck-item sweeper, every 15 minutes
```

Then send a payment the way 5 Series would, or a NAV statement the way the intake system would. Both use the
same token as UC1:

```powershell
$hook = @{ "X-Webhook-Token" = (Get-Content dev\n8n\out\local-secrets.json | ConvertFrom-Json).intake }
Invoke-RestMethod -Method Post http://127.0.0.1:5678/webhook/transaction-received -Headers $hook `
  -ContentType "application/json" -Body '{"transactionId":"TX-DEMO-LARGE-0001","source":"realtime"}'
Invoke-RestMethod -Method Post http://127.0.0.1:5678/webhook/nav-statement-received -Headers $hook `
  -ContentType "application/json" `
  -Body '{"channel":"sftp","objectKey":"raw-docs/uc3/2026/10/mgf-nav.pdf","receivedAt":"2026-10-30T03:00:00Z"}'
```

Locally, a keyword in the transaction ID picks the payment. Use a new ID each time: the same ID is the same
payment, which is what makes n8n's retries safe.

| Keyword in the ID | Payment | Result |
|---|---|---|
| `LARGE` | USD 48,000 to Singapore, within the client's profile | Compliance decision card; approving releases the payment |
| `PEP` | USD 30,000 for a client who is a PEP | Compliance decision card; gate 3's evidence shows the PEP flag |
| `UNUSUAL` | USD 2,500 flagged unusual by 5 Series | Compliance decision card |
| `PROFILE` | USD 15,000 to the UAE, outside the profile | Profile-update card |
| `UNSURE` | USD 18,000, purpose unclear | The model cannot tell, which counts as a mismatch: profile-update card |
| `HIGHRISK` | USD 3,000 to Iran | Monitored for the country, then a profile-update card |
| `SANCTION` | USD 12,000 to Kowloon Trading Ltd | Screening hit: MLRO escalation; approving freezes the payment |
| `SCREENDOWN` | USD 20,000; the screening service is down | Gate-exception card; the payment stays held |
| `INTERNAL` | USD 25,000 to an internal account | Filed below threshold (exclusion list); no card |
| none | USD 1,500 to 8,499 to a supplier | Filed below threshold; no card |

Compliance cards go to Kenneth Ho or Ava Leung, the MLRO escalation to Daniel Wong, each a few seconds after it
is created, once the evidence review has listed the payment, the client profile and the screening on it and
written its summary. A payment that gate 1
monitors is held in 5 Series until its card is decided (locally, the hold, release and freeze are only
logged).

For UC3, the object key picks the fund: `MGF`, `MIF` or `AFS` in the key gives Meridian Growth Fund, Meridian
Income Fund or Ardent Fund SPC. `STALE` (valued 5 business days before it arrived), `JUMP` (NAV up 6.5 %,
beyond every fund's tolerance) or `SHARES` (the share register does not reconcile) gives a NAV exception card.
Anything else gives a NAV approval card for Lars Jansen; approving it publishes the NAV to Valuefy (locally,
only logged). As with payments, use a new object key each time.

The sweeper starts again any statement, payment or extraction job stuck for 30 minutes, and after 3 tries
raises an incident for platform support instead.

## 4. Sign in as a sample officer

Locally there is no Entra tenant. `GET /v1/dev/users` lists the sample officers (the portal's personas), and
`POST /v1/dev/sign-in` with `{ "userId": "..." }` returns a bearer token for one of them, signed with a key the
API makes at start-up (a restart signs everyone out). These two routes exist only when `ENVIRONMENT` is
`local` or `test`.

To use the portal on this data, start it against the backend instead of its demo data, then open
http://localhost:4200 and use **Sign in** (on the UDAP landing page, then on the sign-in page):

```powershell
cd frontend
npm run start:api
```

| Officer | Roles | Team |
|---|---|---|
| Chan Tai Man | Maker | Operations |
| Priya Lam, Ahmed Khan | Checker | Operations |
| Kenneth Ho, Ava Leung | Checker | Compliance |
| Daniel Wong | MLRO | MLRO office |
| Sofia Rossi / Lars Jansen | Maker / Checker | Fund accounting |
| Mei Ling Tan / Ravi Menon | Maker and Checker / Checker | Data team |
| Grace Lee | Admin | Platform |
| Martin de Vries | Auditor | Internal audit |

## 5. Use the real model (ModelArts Studio MaaS)

Locally, card recommendations come from a stand-in that calls no model. To use DeepSeek-V4-Flash on ModelArts
Studio MaaS instead:

1. In the Huawei Cloud console, region **CN-Hong Kong**, open ModelArts Studio (MaaS), then **Model Inference >
   Real-Time Inference > Built-in Services**, and **Subscribe** to DeepSeek-V4-Flash. It is billed per token,
   with nothing to pay while it is idle.
2. On the **API Keys** page, **Create API Key** and paste the key into `backend/.env` as `MAAS_API_KEY`. A new
   key works after a few minutes. Never commit it, or paste it into a chat or a ticket.
3. Check it with `python -m scripts.check_maas`. It makes three small calls with synthetic data (a connectivity
   check, a UC4 recommendation and a UC2 evidence review), and prints the model's answers, the tokens used and
   the cost.
4. Set `MAAS_INTEGRATION=real` in `backend/.env` and restart the API. The other systems stay synthetic
   (`INTEGRATIONS=fake`). Every card now gets the model's summary, proposed action and citations: UC4 and UC5
   from their finding, UC1, UC2 and UC3 from the evidence review the API runs when it creates the card (and
   again on Return-to-AI). Each recommendation stores its prompt version, tokens and cost, and for the evidence
   review the exact evidence the model read, with the card.

**API Calling** on the Real-Time Inference page shows the model name and the URL. `MAAS_MODEL` and
`MAAS_BASE_URL` default to `deepseek-v4-flash` and `https://api-ap-southeast-1.modelarts-maas.com/openai/v1`.
If the check reports that MaaS refused the `thinking` parameter, set `MAAS_THINKING=default`.

From a laptop, the calls go over the Internet to the public endpoint, so send synthetic data only. DEV, NPR
and PRD reach MaaS through a VPC endpoint. No customer data goes to the model until the contract confirms the
MaaS terms (no training on customer data, and how long prompts are kept).

## What works today

| Endpoint | Called by |
|---|---|
| `POST /v1/bank-statements`, `POST /v1/extraction/jobs` (calls n8n back), `POST /v1/gates/evaluate` | UC1 |
| `POST /v1/transactions`, `POST /v1/payment-requests/claim`, `POST /v1/transactions/enrich`, `POST /v1/transactions/{id}/file`, `POST /v1/gates/evaluate` (gates 1 to 3) | UC2 |
| `POST /v1/nav-statements`, `POST /v1/extraction/jobs`, `POST /v1/gates/evaluate` (`nav.checks`) | UC3 |
| `POST /v1/scans`, `GET /v1/scans/{id}`, `GET /v1/scans/{id}/findings` | UC4, UC5 |
| `POST /v1/maintenance/redrive` | Stuck-item sweeper |
| `POST /v1/cards` (all 11 card types), `POST /v1/cards/{id}/recommend` | All workflows; UC4, UC5 |
| `POST /v1/notifications` | Every workflow (delivered by the jobs worker; locally written to the log) |
| `POST /v1/incidents` | Platform error handler |
| `GET /v1/me`, `GET /v1/settings/data-scope`, `GET /v1/card-types` | Portal |
| `GET /v1/cards` (views, filters, paging), `GET /v1/cards/counts`, `GET /v1/cards/{id}` | Portal inbox and card |
| `POST /v1/cards/{id}/decisions`, `GET /v1/cards/{id}/delegates` | Portal decisions |
| `GET /v1/statements/{id}`, `GET .../lines`, `PATCH .../lines/{lineId}`, `POST .../lines/{lineId}/approve`, `PATCH .../references`, `POST .../submit` | Portal validation workspace (UC1) |
| `GET /v1/lookups/en-numbers`, `GET /v1/audit/events` | Portal |
| `GET /v1/incidents/{id}` | Portal (Admin, Auditor, MLRO) |
| `GET /v1/rulesets`; `POST /v1/rulesets/{key}/test`, `.../validate`, `.../versions`; `PUT`, `DELETE .../versions/{version}`; `POST .../versions/{version}/approve` | Portal ruleset administration |
| `GET /v1/dashboard/summary` | Portal KPI dashboard |
| `GET /v1/events/ticket`, `GET /v1/events/stream` | Portal live updates |
| `POST /v1/cards/{id}/assistant` | Portal card assistant |
| (no endpoint) the evidence review of UC1, UC2 and UC3 cards: jobs `card.assemble` and `card.review` | Queued by `POST /v1/cards` and Return-to-AI |
| `GET /health`, `GET /ready` | Infrastructure |

UC1 to UC5 and the stuck-item sweeper run end to end. Locally, `INTEGRATIONS=fake` replaces the data lake,
the extraction service, 5 Series, CARE, World-Check, the model, the write-back, Valuefy and Teams with synthetic
stand-ins (`MAAS_INTEGRATION=real` brings back the real model, section 5), and `EMBEDDED_WORKER=true` runs the
jobs worker inside the API process. Elsewhere, run it separately with `python -m app.workers.jobs`.

Not built yet: the connectors to the real systems (5 Series, CARE, World-Check, the extraction service,
Valuefy, Teams), Entra ID sign-in against the client's tenant, the Huawei Cloud deployment, and CI. Each needs
access the project does not have yet. See `docs/design/platform-api-blueprint.html`.
