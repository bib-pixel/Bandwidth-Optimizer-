# AI-Based Predictive Bandwidth Optimization and Network Traffic Management

## Current capabilities
- Live Scapy/Npcap capture or simulation mode.
- Rule-based traffic classification, explicitly labelled as a baseline.
- Timestamped SQLite network snapshots and hourly/weekday-hour profiles.
- 15-minute Random Forest throughput forecasting when sufficient real, horizon-matched data exists; otherwise an explicit statistical fallback.
- Forecast explanations, peak-hour congestion estimates, chronological holdout MAE, and live forecast-vs-actual MAE after each forecast target time.
- Proactive QoS recommendations. Recommendations are not represented as enforced reservations.
- Optional Linux `tc` interface-wide HTB cap, disabled by default. This is not per-application Priority Queuing (PQ) or Weighted Fair Queuing (WFQ).

## Setup on Windows
1. Create `.env` from `.env.example` and preserve your own secret key.
2. Activate `.venv` and install `requirements.txt`.
3. Run `python app.py` from the project root. For live capture, configure `CAPTURE_MODE=live`, `CAPTURE_INTERFACE=Wi-Fi`, and `CAPTURE_BACKEND=scapy`; run elevated if Npcap requires it.
4. Keep monitoring active over multiple days to learn hourly and weekly patterns. Model training requires at least 100 horizon-matched examples across 3 separate dates.

## QoS safety and enforcement
On Windows, this application provides recommendations only; packet capture via Npcap is not a traffic shaper. On Linux, the optional `/api/qos/apply` endpoint can apply a root HTB interface cap only if `QOS_ENFORCEMENT_ENABLED=true` and `QOS_INTERFACE` are explicitly configured. This replaces the root qdisc and can disrupt existing traffic control, so test only on a controlled host/interface and inspect existing `tc qdisc show dev INTERFACE` / `tc class show dev INTERFACE` first. The provided enforcement is an interface cap, not application-aware PQ/WFQ. It should not be enabled on a production or remote management interface without a rollback plan.

## Forecast evaluation
- Chronological holdout MAE is reported when training is possible.
- Live MAE is calculated from stored forecasts paired with actual snapshots near the target time.
- Do not treat synthetic test results or in-sample scores as evidence of real-network accuracy.
- A peak-hour label estimates throughput divided by configured capacity; it is not a direct queue-depth or packet-loss measurement.

## API additions
- `GET /api/qos/status`: reports enforcement capability and configuration.
- `POST /api/qos/apply`: applies the opt-in Linux HTB cap only when explicitly enabled; otherwise returns a disabled response.
- `GET /api/dashboard`: includes `forecast.live_evaluation` and `qos_policy`.

## Validation performed for this package
Python bytecode compilation and JavaScript syntax validation pass. The full Flask application could not be run in this build environment because Flask is not installed here. Validate locally on the Windows machine before relying on it.


# To run on a new system
# Network Traffic Analyzer and Predictive Bandwidth Optimizer

## Prerequisites
- Windows 10 or 11
- A compatible Python 3 installation
- Wireshark/TShark and Npcap if live packet capture is required

## Setup
1. Extract the ZIP archive.
2. Open PowerShell in the extracted project directory.
3. Create a virtual environment:

   `python -m venv .venv`

4. Activate it:

   `.\.venv\Scripts\Activate.ps1`

5. Install dependencies:

   `python -m pip install --upgrade pip`

   `pip install -r requirements.txt`

6. Configure the environment variables using `.env.example`, if provided.
7. Configure the correct network interface and packet-capture paths if live capture is enabled.

## Run
Start the application:

`python app.py`

Open the dashboard at:

http://127.0.0.1:5000/

Keep the terminal open while using the application.

## Troubleshooting
- If a Python module is missing, confirm the virtual environment is activated and install the dependencies again.
- If live capture fails, verify Npcap is installed, the interface name is correct, and the required permissions are available.
- If the dashboard cannot connect, check the Flask terminal for startup errors and confirm the configured port.
- If the database is missing, follow the project's database initialization instructions.

## Notes
- Live packet capture depends on the recipient's operating system configuration and network interface.
- Synthetic traffic data, if included, is for demonstration and testing.
- QoS recommendations do not necessarily mean network traffic is being actively shaped.
