# Fixed bandwidth forecast test files

Files:
- `historical_predictor.py`: replace `app/services/historical_predictor.py` with this file.
- `seed_synthetic_network_snapshots.py`: safe DB seeder/restorer (backs up DB and only replaces `network_snapshots` + `forecast_evaluations`).
- `synthetic_network_snapshots_7days.csv`: refreshed seven-day synthetic data. Lunch traffic remains high from 1:00–2:00 PM and peaks at 1:30 PM; morning and 4:00–4:15 PM peaks are retained.

## Apply safely (PowerShell, from `C:\minor project`)
1. Stop Flask with `Ctrl+C`.
2. Make a manual copy of `app\services\historical_predictor.py` before replacing it.
3. Copy the fixed predictor into `app\services\historical_predictor.py`.
4. Copy the seeder and CSV into the project root, replacing the old versions only if you intend to run the synthetic test.
5. For a synthetic test, run `..\?` no; use the project venv: `..\.venv\Scripts\python.exe .\seed_synthetic_network_snapshots.py --seed` is only valid if the venv is in the parent directory. Usually use ` .\.venv\Scripts\python.exe .\seed_synthetic_network_snapshots.py --seed`.
6. Restart Flask. Open the dashboard; forecasts should blend the Random Forest with a fine-grained target-time profile when at least two days of matching data exist.
7. After testing, stop Flask and run ` .\.venv\Scripts\python.exe .\seed_synthetic_network_snapshots.py --restore`. This restores the pre-test database backup.

Important: the synthetic dataset is for demonstration only, not evidence of real-world predictive accuracy. The displayed validation MAE is calculated on a chronological holdout from the available dataset and can look unusually low on generated data. QoS remains recommendation-only on Windows; this change does not enable traffic shaping.
