"""Offline scikit-learn training utilities for the included sample dataset."""

from pathlib import Path


def train_models(dataset_path: str, model_directory: str) -> None:
    """Train and save baseline traffic and congestion Random Forest models."""
    import joblib
    import pandas as pd
    from sklearn.ensemble import RandomForestClassifier
    data = pd.read_csv(dataset_path)
    output = Path(model_directory)
    output.mkdir(parents=True, exist_ok=True)
    fields = ["throughput_mbps", "packet_rate", "destination_port", "upload_ratio"]
    traffic_model = RandomForestClassifier(n_estimators=100, random_state=42).fit(data[fields], data["traffic_type"])
    joblib.dump(traffic_model, output / "traffic_classifier.pkl")
    congestion_fields = ["throughput_mbps", "packet_rate", "flow_count", "upload_ratio"]
    congestion_model = RandomForestClassifier(n_estimators=100, random_state=42).fit(data[congestion_fields], data["congestion_level"])
    joblib.dump(congestion_model, output / "congestion_predictor.pkl")
