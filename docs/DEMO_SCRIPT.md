# 3-minute demo script

**Setup before recording:** backend running, dashboard open at http://localhost:8000, phone with the Omi app
visible (screen-mirror it or hold it to the camera), demo data reset (Connections → Reset all data).

| Time | Show | Say |
|---|---|---|
| 0:00 | Title / dashboard | "We make about 20 promises a day out loud and forget half of them. Vachan is an ambient AI that keeps your word for you, built on Omi, Lyzr and Qdrant." |
| 0:15 | Talk to a friend near Omi, or Connections → Play "Coffee with Rahul" | *"Thanks Rahul, I'll send you the updated pitch deck by Thursday evening."* |
| 0:35 | Agent activity page: steps complete one by one | "Omi sends the transcript. PII is masked on-device first. Then the Privacy Guard, Extractor and Curator agents on Lyzr run, with Qdrant as their shared memory." Click the **Promise Extractor** step to show its JSON input and output. |
| 1:00 | Overview: new promises + phone notification | "It knows I owe Rahul the deck on Thursday at 6 PM, and Rahul owes me the investor list tomorrow." |
| 1:10 | Second conversation ("Standup with Priya") | *"Sure Priya, I'll review your PR on Thursday at 6 pm."* |
| 1:25 | "Needs your attention" shows the clash + phone alert | "The Curator retrieved my same-day promises from Qdrant and caught the clash before I double-booked myself." |
| 1:45 | Say: *"Hey Vachan, what do I owe Rahul this week?"* | Answer arrives on the phone. Show the command DAG: Router → Qdrant filtered search → Recall. |
| 2:05 | Play "Call with Arjun", then the Memory and Privacy pages | "Off-the-record speech never got stored. The loan amount and health details were redacted, and that memory is private, so no LLM ever sees it." |
| 2:25 | Say / type: *"Forget what I said about the loan"* | Points deleted from Qdrant, audit log entry appears. |
| 2:40 | Say: *"I sent the pitch deck to Rahul"* | The promise moves to **Kept** and the Overview score ring fills. |
| 2:50 | Architecture diagram (README) | "Six Lyzr agents, two Qdrant collections, one voice loop. Your word, kept." |
