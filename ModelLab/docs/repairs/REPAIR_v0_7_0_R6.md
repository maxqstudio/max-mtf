# CPMF v0.7.0 R6 — Background Discovery + Live Leaderboard Repair

## Closed regressions

1. Champion Factory Discovery no longer runs inside the Streamlit script lifecycle. Discovery is launched as a separate Python worker process. Navigation, refresh, or returning to Discovery does not stop the worker. Only the explicit STOP RESEARCH control requests termination.
2. Discovery restores the live candidate leaderboard. Every completed candidate is persisted to a job-scoped candidate evidence file and displayed again after navigation/rerun.
3. Champion Factory disables first-winner/patience early-stop authority inside each Discovery generation. A qualified candidate adds to the pool; it does not end pool building. Discovery terminates only on pool target, bounded experiment/generation budget, explicit stop, or fatal error.
4. Factory progress and event history are persisted to disk and polled by a Streamlit fragment every two seconds; the UI thread is never the training worker.

## Authority

Normal route remains Data → Discovery → Pool → Tournament → Fresh → Champion. CV/OOF/Scientist remain internal Discovery mechanics. Tournament and Fresh remain untouched by Discovery feedback.
