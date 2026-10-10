# Deploying Vachan (Modal + Vercel)

| Part | Host | URL |
|---|---|---|
| API, agents, webhooks, scheduler | Modal | `https://yakshmajas--vachan-api.modal.run` |
| Dashboard | Modal (same URL) or Vercel | `https://yakshmajas--vachan-api.modal.run` |
| Vector memory | Qdrant Cloud | from `QDRANT_URL` |

## Backend on Modal
```bash
cd backend
.venv\Scripts\pip install modal
.venv\Scripts\modal token new          # once: browser login
set MODAL_PROFILE=yakshmajas
.venv\Scripts\modal deploy modal_app.py
```
Rebuild the dashboard first (`cd frontend && npm run build`). The deploy bundles `frontend/dist`, so the
dashboard is served from the same URL.
- Keys are read from `backend/.env` at deploy time (`modal.Secret.from_dotenv`). **Redeploy after
  changing `.env`.**
- It runs as **one always-warm container** (`min_containers=1`, `max_containers=1`). The wake-phrase
  listener, reminder scheduler and live trace stream keep state in memory, and Omi webhooks must never
  hit a cold start. Cost is about one small CPU container, well within Modal's free monthly credit.
- The audit log and traces persist on the Modal Volume `vachan-data`.
- Check it: `https://yakshmajas--vachan-api.modal.run/api/health`

## Dashboard on Vercel
```bash
cd frontend
npx vercel login                # once
npx vercel deploy --prod
```
`frontend/.env.production` points the build at the Modal API (`VITE_API_BASE`). The API allows any
`https://*.vercel.app` origin (`VACHAN_CORS_ORIGIN_REGEX`).

## Omi
In the Omi app (Developer Settings, or your app's External Integration):
| Trigger | URL |
|---|---|
| Conversation created | `https://yakshmajas--vachan-api.modal.run/omi/conversation` |
| Real-time transcript | `https://yakshmajas--vachan-api.modal.run/omi/realtime` |

Phone notifications additionally need `OMI_APP_ID` and `OMI_APP_SECRET` in `backend/.env`, then a
redeploy.

## Don't run two backends at once
The local server and Modal share the same Qdrant data. If both run, reminders fire twice. Use the local
server only for development, ideally with a separate Qdrant collection or local storage
(leave `QDRANT_URL` empty).
