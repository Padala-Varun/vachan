# Connecting Omi (about 10 minutes)

**What Omi is:** an open-source AI wearable (a small pendant) plus a free phone app. It listens to your
conversations and transcribes them live. Developers build "Omi apps" that receive those transcripts through
**webhooks** (HTTP calls to your server). Vachan is such an app.

## 1. Expose your laptop to the internet
Omi's cloud must be able to reach your backend. Use a free tunnel:
```bash
# option A
ngrok http 8000
# option B
cloudflared tunnel --url http://localhost:8000
```
Copy the public `https://....` URL. Below it's called `PUBLIC_URL`.

## 2. Create the Omi app
1. Install the **Omi** app (Android / iOS) and sign in. If you have the pendant, pair it.
   Without the pendant, check whether your app version can record with the phone microphone.
   Otherwise use `scripts/simulate_omi.py`, which sends the exact same payloads.
2. In the Omi app go to **Apps → Create app**.
3. Choose capability **External Integration** and enable both triggers:
   | Trigger | Webhook URL |
   |---|---|
   | Conversation creation | `PUBLIC_URL/omi/conversation` |
   | Real-time transcript | `PUBLIC_URL/omi/realtime` |
   Setup-completed URL (if asked): `PUBLIC_URL/omi/setup-complete`
4. Enable **Notifications** for the app if offered.
5. Save. Keep the app private, then install/enable it on your account.
6. Copy the **App ID** and **App Secret** (developer settings) into `backend/.env`:
   ```
   OMI_APP_ID=...
   OMI_APP_SECRET=...
   ```

## 3. Find your Omi user id
Have any conversation. The server log shows `POST /omi/conversation?uid=XXXX`. Set that value as
`VACHAN_DEFAULT_UID` in `backend/.env` so the dashboard and simulator use your real memory.

## 4. Test the loop
1. Restart the backend. The dashboard pill should show **Omi · connected**.
2. Say near the device: *"Rahul, I'll send you the pitch deck by Thursday evening."*
   When Omi finishes the conversation (after a short silence), the DAG lights up and a push lands on your phone.
3. Say: *"Hey Vachan, what do I owe Rahul this week?"* The answer arrives as a notification.

## Tips
- The wake phrase is matched in the live transcript. If Omi hears "Vachan" differently, add that spelling to
  `VACHAN_WAKE_PHRASES` in `.env` (e.g. `hey vachan,bachan,watchin`). `hey promise keeper` is a reliable
  English fallback.
- Omi closes a conversation after a period of silence. For demos, use Omi's option to end a conversation
  manually, or play the fixtures with the simulator.
