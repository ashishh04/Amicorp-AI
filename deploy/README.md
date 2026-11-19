# Deploying UDAP on a server

This puts the platform on one Linux server with Docker and connects it to the n8n you already deployed:

```
 people ── HTTPS ──►  gateway (Caddy, ports 80/443)
                        ├─ /api/*  ──►  platform-api (port 8000, with its jobs worker)  ──►  PostgreSQL, Redis
                        └─ the rest ──►  portal (nginx): Work Card Portal and the UDAP landing page

 your n8n  ── Bearer token ──►  platform-api (port 8000)          n8n calls the API
 your n8n  ◄── X-Webhook-Token ──  platform-api                   the API calls n8n back after an extraction
```

The simplest layout is the same server as n8n: nothing new to pay for, and the two talk over the server's
private address. The steps below assume it; where another layout differs, the step says so.

## Read this first: it is the demo configuration

The API runs with `ENVIRONMENT=local`, the same mode as on the laptop. Any other mode needs Entra ID sign-in
and the connectors to the real systems (5 Series, CARE, World-Check, the extraction service, Valuefy, Teams),
and those are not built yet. So on this server:

- **Nobody types a password.** Anyone who can open the address can sign in as any of the 12 sample officers,
  the Admin and the MLRO included. Access is limited by network address only (step 1 and `ALLOWED_IPS`).
- **Synthetic data only.** Every outside system is a stand-in, except the model if you switch it on (step 9).
- **The portal needs HTTPS.** On plain `http://<IP>` the browser shows "The portal could not start". Use a DNS
  name, or the server's IP address with the gateway's own certificate, or an SSH tunnel (step 6).
- A restart of the API signs everyone out (the sign-in key lives in memory).

It is the right setup for a demo or a team test server. It is not DEV, NPR or PRD.

## The short version

Push the code from the laptop (step 2), open port 443 in the cloud firewall (step 1), then on the server:

```bash
git clone <your repository URL> ~/udap        # the first time; later:  git -C ~/udap pull
cd ~/udap/deploy
python3 deploy.py                                          # n8n runs on this server
python3 deploy.py --n8n-url http://<n8n's address>:5678    # n8n runs on another server
```

`deploy.py` runs steps 3 to 8 below in order. It stops at the first step that fails, says which one and what to
do, and is safe to run again: a finished step is quick the second time, and nothing that is already set (the
secrets, n8n's workflows) is replaced. It asks the cloud for this server's public address; `--site <DNS name>`
names another address for people to open. `--allow <address>` lets another public address open the portal;
`--skip-n8n` leaves n8n alone. It ends with `DEPLOYED` and the address to open.

With n8n on another server there are two more things, and the command names both when it reaches them: this
server's firewall must let the n8n server reach port 8000, and the workflows are loaded on the n8n server with
two commands that it prints for your laptop.

The steps below describe what it does, for when you want to run one by hand.

## Step 1. The firewall

Set the cloud firewall (in AWS: the instance's security group, **Edit inbound rules**) before you start
anything. Ports that Docker publishes ignore `ufw`, so the security group is what protects the server.

| Port | Open it to | Why |
|---|---|---|
| 22 | your own address | SSH |
| 443 | the people who may use the portal ("My IP") | The portal (HTTPS) |
| 80 | the same people; **everyone** if `SITE_ADDRESS` is a DNS name | Redirect to HTTPS, and the certificate check |
| 8000 | nobody when n8n is on this server; otherwise the n8n server's address only | n8n calls the API |
| 5678 | your own address (n8n's sign-in travels unencrypted on plain HTTP) | The n8n editor |

## Step 2. Get the platform onto the server

**With git.** On the laptop, once, in PowerShell:

```powershell
cd D:\Amicorp-AI
git init -b main
git add .gitignore backend frontend deploy dev n8n-workflows
git commit -m "UDAP platform: API, portal, n8n workflows, deployment"
git remote add origin <your repository URL>
git push -u origin main
```

Use a **private** repository. The `.gitignore` files keep every secret out (`backend\.env`, the n8n tokens, the
server's `.env`), and these commands add the code only: `docs`, `datasets` and `demo-pitch` hold client documents
and stay on the laptop unless you add them yourself. Then, on the server:

```bash
git clone <your repository URL> ~/udap
cd ~/udap/deploy
```

For a private repository, git asks for a user name and a personal access token (not the account password).

**Without git.** `.\deploy\make-bundle.ps1` on the laptop packs the same files into `deploy\udap-deploy.tar.gz`.
Copy it with `scp -i <your-key.pem> .\deploy\udap-deploy.tar.gz ubuntu@<server>:~/`, then on the server:
`mkdir -p ~/udap && tar -xzf ~/udap-deploy.tar.gz -C ~/udap && cd ~/udap/deploy`.

## Step 3. Check the server

```bash
python3 preflight.py
```

It changes nothing. It reports memory, disk, Docker, the ports and where n8n runs, each line marked OK, NOTE or
FIX, and ends with `RESULT`. Fix the FIX lines (it prints the commands, for example to add swap on a small
server, or to install Docker or its Compose and buildx plugins), then run it again until it says the server is
ready. If this user may reach Docker only through `sudo`, the scripts use `sudo` themselves and say so.

The platform needs about 1 GB of memory to run, and about 3 GB of free memory and swap together for the first
build. If a NOTE says n8n keeps its data inside its container, never remove that container; nothing in these
steps does.

## Step 4. Settings

```bash
python3 new_env.py                                          # n8n runs on this server
python3 new_env.py --n8n-url http://<n8n's address>:5678    # n8n runs on another server
```

It creates `.env`: a new database password, four new tokens, and the addresses. It asks the cloud for this
server's public address (`--site` names a DNS name instead), and it allows the address you are connected from to
open the portal. It prints what it chose. `--allow 203.0.113.7/32` allows another address (repeat it for more).
Running it again completes the same file: a secret or an n8n address that is already set is never replaced,
unless you give `--site` or `--n8n-url` again.

With a DNS name the gateway fetches a public certificate. With an IP address it signs its own, and the browser
warns once. If the public IP changes (an AWS instance without an Elastic IP gets a new one after a stop), run
`python3 deploy.py` again: it corrects the address.

What the script writes:

| Where n8n runs | `N8N_WEBHOOK_BASE` | `PLATFORM_API_URL` | `API_BIND` |
|---|---|---|---|
| On this server (in Docker or not) | `http://<this server's private IP>:5678` | `http://<this server's private IP>:8000` | `0.0.0.0` |
| On another server, given by a private address | `--n8n-url` | `http://<this server's private IP>:8000` | `0.0.0.0` |
| On another server, given by a public address | `--n8n-url` | `http://<this server's public address>:8000` | `0.0.0.0` |

With n8n on another server, the firewalls must allow both directions: port 8000 of this server from the n8n
server, and n8n's port from this server. Use the private addresses when both servers are in the same network:
they do not change when a server is stopped, and the tokens do not cross the Internet. With public addresses on
plain HTTP they do, which is acceptable for synthetic data only.

## Step 5. Start

```bash
docker compose up -d --build                    # the first time takes 5 to 10 minutes
docker compose ps                               # api, portal, postgres, redis: healthy; migrate: exited (0)
docker compose exec api python -m scripts.seed  # sample officers and reference data; safe to run again
curl -s http://127.0.0.1:8000/ready
```

The seed answers `Seeded 12 users, 10 enNumbers, 2 banks, 5 rulesets`, and `/ready` answers
`{"status":"ready","checks":{"database":"ok","redis":"ok"}}`. The database tables are created by the `migrate`
service on every start, before the API.

## Step 6. Open the portal

Browse to `https://<SITE_ADDRESS>`. With an IP address the browser warns about the certificate once: choose
**Advanced**, then **Proceed**. You see the UDAP landing page; **Sign in**, **Sign in** again, then choose an
account, for example Chan Tai Man.

A visitor whose address is not allowed gets a 403 that names the address. Add it to `ALLOWED_IPS` in `.env`
(separated by a space), then run `docker compose up -d`.

Without opening any port, from your own PC: `ssh -i <your-key.pem> -L 8080:127.0.0.1:80 ubuntu@<server>`, leave it
open, and browse to http://localhost:8080.

## Step 7. Connect n8n

```bash
python3 n8n/make_server_workflows.py
python3 n8n/import_to_n8n.py
```

The first command writes `n8n/out/`: the seven workflows and four credentials for this server. n8n Community
Edition has no Variables, so the addresses and limits are written into the copies; nothing changes in n8n's own
settings. The second command finds the n8n container, shows what it will do and asks before it starts. It adds
the credentials and workflows, publishes the seven, and restarts the container (about half a minute without
n8n). It never removes the container. It ends with `DONE` when the webhooks answer.

It stops, without changing anything, if n8n already has workflows with the same names under other IDs: two
copies would answer the same webhook address. Unpublish or delete those in the n8n editor, then run it again.

**n8n on another server:** `deploy.py` puts the script, its helper and the copies into `n8n-transfer/` and prints
two commands for your laptop, which can reach both servers. The first copies that folder from this server to
the n8n server; the second runs the import there and removes the folder:

```powershell
scp -3 -r -i <your-key.pem> ubuntu@<this server>:udap/deploy/n8n-transfer ubuntu@<n8n server>:udap-n8n
ssh -i <your-key.pem> ubuntu@<n8n server> "python3 udap-n8n/import_to_n8n.py --yes && rm -rf udap-n8n"
```

Then press Enter in `deploy.py`: it checks that n8n has the workflows with the current credentials and goes on.

**n8n without Docker, or if you prefer to type it:** these are the commands the script runs (in a container,
each one after `docker exec <n8n>`; the files must first be copied into the container with `docker cp`).

```bash
n8n import:credentials --input=n8n/out/credentials.json
n8n import:workflow --separate --input=n8n/out/workflows
for id in AmiErrHandler001 vPwRzUT00rVmHcz6 DtzF1bAiEVG1FokV 1F66HcgBhqJULu2Z fyQwsorpSYUZmJsU wspq7Ik3sHsuiTwC rwIQ665J6hDgTXYq; do
  n8n publish:workflow --id=$id        # n8n 1.x: n8n update:workflow --id=$id --active=true
done
```

Then restart n8n: a publish from the command line takes effect at start-up.

## Step 8. Test it end to end

```bash
python3 send_test.py
```

It sends a bank statement to n8n the way the intake system would, then waits for the Platform API to extract
it, call n8n back and create the card. It ends with `PASSED` and the card's title, or says what to look at.
Then sign in to the portal as the owner it names: the card is there.

A payment for UC2, by hand:

```bash
N8N=$(grep '^N8N_WEBHOOK_BASE=' .env | cut -d= -f2-)
TOKEN=$(grep '^N8N_INTAKE_WEBHOOK_TOKEN=' .env | cut -d= -f2-)
curl -sS -X POST "$N8N/webhook/transaction-received" \
  -H "X-Webhook-Token: $TOKEN" -H "Content-Type: application/json" \
  -d "{\"transactionId\":\"TX-DEMO-LARGE-$(date +%s)\",\"source\":\"realtime\"}"
```

That one gives a compliance decision card for Kenneth Ho or Ava Leung. `dev/README.md` lists the other payment
keywords and the NAV statements (UC3). The helpers in `demo-pitch/_tools/demo.ps1` talk to the laptop
(`127.0.0.1`), not to this server.

## Step 9. Switch on the real model (optional)

Without this, card summaries come from a stand-in that calls no model. In `.env`, paste the ModelArts Studio
MaaS key between the quotes of `MAAS_API_KEY=''` (the same key as in `backend\.env` on the laptop works). Then:

```bash
docker compose run --rm api python -m scripts.check_maas    # three small calls with synthetic data
nano .env                                                    # MAAS_INTEGRATION=real
docker compose up -d
```

The server must be able to reach `api-ap-southeast-1.modelarts-maas.com` on port 443. Send synthetic data only.

## Day to day

| Task | Command (in `~/udap/deploy`) |
|---|---|
| Status | `docker compose ps` |
| Logs | `docker compose logs -f api` (also `gateway`, `portal`, `postgres`) |
| Changed `.env` | `docker compose up -d`; if an address or a token changed, step 7 again |
| New code | Laptop: `git add -A backend frontend deploy dev n8n-workflows`, `git commit -m "..."`, `git push`. Server: `git -C ~/udap pull`, then `docker compose up -d --build` (`.env` and the database are kept). If a workflow changed, step 7 again. |
| Backup | `docker compose exec -T postgres pg_dump -U amc amicorp \| gzip > udap-$(date +%F).sql.gz` |
| Stop | `docker compose down` (data kept). `docker compose down -v` deletes the database. |

`docker compose` here only ever touches the platform's own containers, never n8n.

## If something goes wrong

| What you see | Cause and fix |
|---|---|
| "The portal could not start" | The page was opened on plain `http://<IP>`. Use `https://`, or the SSH tunnel of step 6. |
| 403 "not on the server's allow-list" | Add the address it names to `ALLOWED_IPS`, then `docker compose up -d`. |
| The browser cannot connect at all | Port 443 is closed in the security group for your address (step 1), or the gateway is not running: `docker compose ps`. |
| Certificate error with a DNS name | The certificate could not be fetched: the name must point at this server and port 80 must be open to everyone. See `docker compose logs gateway`. |
| The sign-in page says the Platform API did not answer | `docker compose ps`, then `docker compose logs api`. |
| Everybody was signed out | The API restarted. Sign in again. |
| `send_test.py`: n8n does not know the webhook | The workflows are not published, or n8n is still starting: step 7 again. |
| `send_test.py`: n8n refused the token | The tokens in `.env` changed after the import: step 7 again. |
| `send_test.py`: n8n answered HTTP 500 | n8n cannot reach the API at `PLATFORM_API_URL`. Open the failed execution in the n8n editor; check `docker compose ps`. |
| `send_test.py`: accepted, but no card | The API cannot reach n8n at `N8N_WEBHOOK_BASE`: `docker compose logs api \| grep -i callback`. If n8n runs without Docker on this server and `ufw` is on: `sudo ufw allow from 172.16.0.0/12 to any port 5678 proto tcp`. |
| An n8n node gets 401 from the API | The token in `.env` changed after the import: step 7 again. |
| 422 `CALLBACK_NOT_ALLOWED` in n8n | `N8N_WEBHOOK_BASE` changed after the import: step 7 again. |
| The build stops, or the server freezes during it | Too little memory or disk: `python3 preflight.py`. |

## What was checked

On 19 Nov 2026 the compose stack was run from the bundle in Docker, with a separate n8n 2.22.6 standing in for
the n8n server: the build, the migrations and the seed; the portal and the sign-in through the gateway; HTTPS on
an IP address, the redirect from HTTP and the tunnel address; the live event stream; the import and publishing
of the seven workflows; and a bank statement from the n8n webhook to its card.

Added later that day and checked without a server: `deploy.py` (the order of its steps and where it stops),
`preflight.py`, `new_env.py`, `n8n/import_to_n8n.py` (against simulated servers, among them one where Docker needs
`sudo` and one with a half-filled `.env`) and `send_test.py` (against a simulated n8n and API). `preflight.py` and
`new_env.py` also ran on a real Ubuntu 26.04 without Docker. The workflow copies with the
values written in were imported into n8n 2.22.6, and one of them (the sweeper, started by hand) was run there
against a stand-in API: n8n called the written-in address with the imported credential and the written-in
limits. The other six copies have the same structure as the ones that ran end to end earlier.

The path with n8n on another server (the settings, the folder for the n8n server, the two printed commands, the
check that n8n has the current credentials) was checked the same way: against simulated servers and on that
Ubuntu, not between two real servers. `portal.Dockerfile` is `frontend/Dockerfile` plus one line that enlarges
Node's memory limit; it has not been built since that line was added.

Not checked anywhere yet: a public certificate for a DNS name, the allow-list against a real outside address,
n8n in a container (`docker cp` and `docker exec`), the readiness check on a real Linux server, and the model
check from inside the container. `send_test.py` is the proof on the real server.
