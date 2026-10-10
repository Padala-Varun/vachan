# Setting up the six Lyzr agents (about 15 minutes)

Vachan calls each agent through Lyzr's inference API with a JSON message and expects JSON back.
Each agent's full instructions are in [`backend/app/agents/`](../backend/app/agents/).

## 1. Get your API key
1. Sign in at **https://studio.lyzr.ai**.
2. Open your account / settings menu and copy the **API key**.
3. Put it in `backend/.env` as `LYZR_API_KEY=...`.

## 2. Create the agents
Repeat these steps for each row below: **Agents → Create agent**.

| Agent name in Studio | Prompt file | `.env` variable |
|---|---|---|
| Vachan Privacy Guard | `privacy_guard.md` | `LYZR_PRIVACY_GUARD_AGENT_ID` |
| Vachan Promise Extractor | `extractor.md` | `LYZR_EXTRACTOR_AGENT_ID` |
| Vachan Curator | `curator.md` | `LYZR_CURATOR_AGENT_ID` |
| Vachan Nudger | `nudger.md` | `LYZR_NUDGER_AGENT_ID` |
| Vachan Router | `router.md` | `LYZR_ROUTER_AGENT_ID` |
| Vachan Recall | `recall.md` | `LYZR_RECALL_AGENT_ID` |

For each agent:
- **Name / description**: from the table above.
- **Role**: copy the `## Role` section of the prompt file.
- **Instructions**: copy the `## Instructions` and `## Output` sections. Pasting the whole file also works.
- **Model**: any strong model available in your workspace (a GPT-4o-class or Claude model). Use a low
  temperature (0–0.2), because these agents must return strict JSON.
- **Response format / Structured output**: **turn it off** (plain text), or pick a generic "JSON object" mode.
  Do **not** keep a custom schema. Studio's sample schema (`tweet`, `title`) overrides the prompt, so the
  agent answers in the wrong shape. The prompt already asks for the exact JSON.
- Leave tools, knowledge base and memory **off**. Vachan supplies context from Qdrant itself.
- **Save**, then open **Agent API** and copy the **agent ID** into `backend/.env`.

## 3. Check the endpoint
Open the **Agent API** panel of any agent and look at the example `curl`:
- If the URL differs from `https://agent-prod.studio.lyzr.ai/v3/inference/chat/`, set `LYZR_CHAT_URL` to it.
- Vachan sends `{"user_id", "agent_id", "session_id", "message"}` with header `x-api-key`.
  If your panel's example uses different field names, tell Claude and it will adjust
  `backend/app/lyzr_client.py`.

## 4. Verify
Test every configured agent with a realistic sample (from the repo root):
```bash
backend\.venv\Scripts\python scripts/check_lyzr.py
```
Each agent prints `PASS`, `FAIL` (with the reason and the raw reply), or `SKIP` (no ID yet).

Then restart the backend and open http://localhost:8000/api/health:
```json
"agents": {"privacy_guard": "lyzr", "extractor": "lyzr", ...}
```
Run the simulator. In the dashboard, each agent node should show **Lyzr · live**. If a node shows
**Lyzr → fallback**, the server log prints the reason (usually the wrong agent ID or reply format).

## Optional: Manager agent
In Studio you can make **Vachan Router** a *Manager Agent* and attach Recall as a managed agent
(`usage_description`: "answers questions about the user's promises from retrieved memories").
Vachan's orchestrator already performs the delegation, so this step is optional.
