"""Trained short-horizon forecasting with hourly/weekly profiles and explanations.

The model trains on stored snapshots (which may be real or test data). Keep synthetic test data isolated and restore the database afterward. Until enough future-labelled examples exist, it uses an explainable trend/profile baseline.
"""
from __future__ import annotations
from collections import defaultdict
from bisect import bisect_left
from datetime import datetime, timezone, timedelta
from math import isfinite, sin, cos, pi
from statistics import mean
from threading import RLock

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

from app.models import NetworkSnapshot, ForecastEvaluation, db

FEATURES = ["throughput_now", "packet_rate", "flow_count", "usage_percent", "hour_sin", "hour_cos",
            "weekday_sin", "weekday_cos", "target_hour_sin", "target_hour_cos",
            "target_weekday_sin", "target_weekday_cos", "lag_5m", "lag_15m", "mean_5m", "mean_15m"]


class HistoricalCongestionPredictor:
    _cache = {}
    _lock = RLock()

    def __init__(self, horizon_seconds: int = 900, history_limit: int = 25000):
        self.horizon_seconds = horizon_seconds
        self.history_limit = history_limit

    @staticmethod
    def _local_dt(value: datetime) -> datetime:
        value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        return value.astimezone()

    @staticmethod
    def _feature_values(rows, index, capacity, horizon_seconds=900):
        row = rows[index]
        dt = HistoricalCongestionPredictor._local_dt(row.created_at)
        ts = dt.timestamp()
        def nearest_before(seconds):
            for previous_index in range(index - 1, -1, -1):
                previous = rows[previous_index]
                age = ts - HistoricalCongestionPredictor._local_dt(previous.created_at).timestamp()
                if age > seconds + 60:
                    break
                if 0 <= age <= seconds + 60:
                    return max(0.0, float(previous.throughput_mbps))
            return max(0.0, float(row.throughput_mbps))
        def values_before(seconds):
            values = []
            for previous_index in range(index - 1, -1, -1):
                previous = rows[previous_index]
                age = ts - HistoricalCongestionPredictor._local_dt(previous.created_at).timestamp()
                if age > seconds:
                    break
                if age >= 0:
                    values.append(max(0.0, float(previous.throughput_mbps)))
            return values
        day_fraction = (dt.hour * 3600 + dt.minute * 60 + dt.second) / 86400
        week_fraction = (dt.weekday() + day_fraction) / 7
        target_dt = dt + timedelta(seconds=horizon_seconds)
        target_day_fraction = (target_dt.hour * 3600 + target_dt.minute * 60 + target_dt.second) / 86400
        target_week_fraction = (target_dt.weekday() + target_day_fraction) / 7
        recent5, recent15 = values_before(300), values_before(900)
        return [max(0.0, float(row.throughput_mbps)), max(0.0, float(row.packet_rate)), max(0, int(row.flow_count)),
                max(0.0, float(row.throughput_mbps)) / capacity * 100,
                sin(2*pi*day_fraction), cos(2*pi*day_fraction), sin(2*pi*week_fraction), cos(2*pi*week_fraction),
                sin(2*pi*target_day_fraction), cos(2*pi*target_day_fraction),
                sin(2*pi*target_week_fraction), cos(2*pi*target_week_fraction),
                nearest_before(300), nearest_before(900), mean(recent5) if recent5 else float(row.throughput_mbps),
                mean(recent15) if recent15 else float(row.throughput_mbps)]

    def _train_if_possible(self, rows, capacity):
        # Label each snapshot with the measured throughput closest to the forecast horizon.
        pairs_x, pairs_y, pair_dates = [], [], set()
        timestamps = [self._local_dt(r.created_at).timestamp() for r in rows]
        # Downsample training origins to at most one per minute; the forecast target
        # remains the nearest real observation to the configured horizon.
        last_origin = -float("inf")
        for i, ts in enumerate(timestamps):
            if ts - last_origin < 60:
                continue
            target = ts + self.horizon_seconds
            j = bisect_left(timestamps, target, lo=i + 1)
            candidates = [k for k in (j - 1, j) if i < k < len(timestamps)]
            if not candidates:
                continue
            j = min(candidates, key=lambda k: abs(timestamps[k] - target))
            if abs(timestamps[j] - target) > max(90, self.horizon_seconds * 0.20):
                continue
            pairs_x.append(self._feature_values(rows, i, capacity, self.horizon_seconds))
            pairs_y.append(max(0.0, float(rows[j].throughput_mbps)))
            pair_dates.add(self._local_dt(rows[i].created_at).date())
            last_origin = ts
        if len(pairs_x) < 100 or len(pair_dates) < 3:
            return None, {"trained": False, "training_samples": len(pairs_x), "training_days": len(pair_dates), "reason": "Need at least 100 horizon-matched examples across 3 separate dates."}
        x, y = np.asarray(pairs_x, dtype=float), np.asarray(pairs_y, dtype=float)
        # Chronological holdout avoids reporting random-split leakage on time series.
        split = max(int(len(x) * 0.8), 1)
        model = RandomForestRegressor(n_estimators=120, min_samples_leaf=3, max_features=0.9,
                                      random_state=42, n_jobs=-1)
        model.fit(x[:split], y[:split])
        metrics = {"trained": True, "training_samples": int(split), "validation_samples": int(len(x)-split),
                   "training_days": len(pair_dates), "validation_mae_mbps": round(float(mean_absolute_error(y[split:], model.predict(x[split:]))), 4) if len(x)-split else None,
                   "model": "RandomForestRegressor", "target": f"throughput after {self.horizon_seconds//60} minutes"}
        # Refit on all available labelled history after the chronological validation score is recorded.
        model.fit(x, y)
        return (model, metrics), metrics

    def observe_and_predict(self, throughput: float, packet_rate: float, flow_count: int, capacity_mbps: float) -> dict:
        capacity = max(float(capacity_mbps), 0.1)
        now = datetime.now(timezone.utc)
        latest = NetworkSnapshot.query.order_by(NetworkSnapshot.created_at.desc()).first()
        latest_time = None
        if latest:
            latest_time = latest.created_at.replace(tzinfo=timezone.utc) if latest.created_at.tzinfo is None else latest.created_at
        if latest_time is None or (now-latest_time).total_seconds() >= 10:
            db.session.add(NetworkSnapshot(created_at=now, throughput_mbps=max(0.0,float(throughput)),
                packet_rate=max(0.0,float(packet_rate)), flow_count=max(0,int(flow_count)),
                usage_percent=max(0.0,float(throughput))/capacity*100))
            db.session.commit()
        history = (NetworkSnapshot.query.filter(NetworkSnapshot.created_at >= now-timedelta(days=90))
                   .order_by(NetworkSnapshot.created_at.asc()).limit(self.history_limit).all())
        current_usage = max(0.0,float(throughput))/capacity*100
        # Pair due forecasts with the nearest available actual snapshot, once only.
        pending = ForecastEvaluation.query.filter(ForecastEvaluation.actual_throughput_mbps.is_(None), ForecastEvaluation.target_at <= now).order_by(ForecastEvaluation.target_at.asc()).limit(500).all()
        for record in pending:
            actual = min(history, key=lambda r: abs((self._local_dt(r.created_at)-self._local_dt(record.target_at)).total_seconds()), default=None)
            if actual is not None and abs((self._local_dt(actual.created_at)-self._local_dt(record.target_at)).total_seconds()) <= max(180, self.horizon_seconds * .3):
                record.actual_throughput_mbps = max(0.0, float(actual.throughput_mbps))
                record.absolute_error_mbps = abs(record.actual_throughput_mbps - record.predicted_throughput_mbps)
                record.evaluated_at = now
        if pending:
            db.session.commit()
        if len(history) < 5:
            return self._not_ready(len(history), current_usage)

        hourly, weekly, hour_dates, weekly_dates = defaultdict(list), defaultdict(list), defaultdict(set), defaultdict(set)
        for row in history:
            local = self._local_dt(row.created_at); value=max(0.0,float(row.throughput_mbps))
            hourly[local.hour].append(value); weekly[(local.weekday(),local.hour)].append(value)
            hour_dates[local.hour].add(local.date()); weekly_dates[(local.weekday(),local.hour)].add(local.date())
        target_dt = now.astimezone()+timedelta(seconds=self.horizon_seconds)
        h, wd = target_dt.hour, target_dt.weekday()
        hourly_avg = mean(hourly[h]) if len(hour_dates[h]) >= 2 else None
        weekly_avg = mean(weekly[(wd,h)]) if len(weekly_dates[(wd,h)]) >= 2 else None
        # Fine-grained profile around the forecast target (±7 minutes). Unlike an
        # hourly mean, this preserves narrow peaks such as a 13:30 congestion peak.
        target_minute = target_dt.hour * 60 + target_dt.minute
        window_values, weekly_window_values = [], []
        window_dates, weekly_window_dates = set(), set()
        for row in history:
            local = self._local_dt(row.created_at)
            minute = local.hour * 60 + local.minute
            delta = abs(minute - target_minute)
            delta = min(delta, 1440 - delta)
            if delta <= 7:
                window_values.append(max(0.0, float(row.throughput_mbps)))
                window_dates.add(local.date())
                if local.weekday() == wd:
                    weekly_window_values.append(max(0.0, float(row.throughput_mbps)))
                    weekly_window_dates.add(local.date())
        target_window_avg = mean(window_values) if len(window_dates) >= 2 else None
        weekly_window_avg = mean(weekly_window_values) if len(weekly_window_dates) >= 2 else None

        recent = history[-min(30,len(history)):]
        xs=[self._local_dt(r.created_at).timestamp() for r in recent]; ys=[max(0.0,float(r.throughput_mbps)) for r in recent]
        base=xs[0]; xs=[t-base for t in xs]; mx,my=mean(xs),mean(ys)
        den=sum((x-mx)**2 for x in xs); slope=sum((x-mx)*(y-my) for x,y in zip(xs,ys))/den if den else 0.0
        trend=max(0.0,my+slope*((xs[-1]+self.horizon_seconds)-mx))
        if not isfinite(trend): trend=ys[-1]

        # Cache/retrain at most once per 50 new snapshots; training is data-driven.
        key=(id(db.engine), self.horizon_seconds)
        with self._lock:
            cached=self._cache.get(key)
            if cached is None or len(history)-cached.get("trained_at_count",0) >= 50:
                result, metrics=self._train_if_possible(history,capacity)
                cached={"bundle":result,"metrics":metrics,"trained_at_count":len(history)}
                self._cache[key]=cached
        bundle=cached["bundle"]
        model_used=False; contributions=[]
        if bundle and bundle[0] is not None:
            model, metrics=bundle
            x=np.asarray(self._feature_values(history,len(history)-1,capacity,self.horizon_seconds),dtype=float).reshape(1,-1)
            trained_prediction=max(0.0,float(model.predict(x)[0]))
            # Local perturbation explanation: replace each feature with its historical median.
            base_prediction=float(model.predict(x)[0]); impacts=[]
            med=np.median(np.asarray([self._feature_values(history,i,capacity,self.horizon_seconds) for i in range(max(0,len(history)-min(500,len(history))),len(history))]),axis=0)
            for k,name in enumerate(FEATURES):
                changed=x.copy(); changed[0,k]=med[k]
                delta=base_prediction-float(model.predict(changed)[0])
                if abs(delta)>1e-5: impacts.append((name,delta))
            impacts.sort(key=lambda p:abs(p[1]),reverse=True)
            contributions=[{"factor":name.replace('_',' ').title(),"direction":"risk" if delta>0 else "relief",
                            "detail":f"The current {name.replace('_',' ')} contributes approximately {delta:+.3f} Mbps relative to its recent median, using one-feature-at-a-time perturbation."}
                           for name,delta in impacts[:4]]
            # Blend the learned forecast with repeated time-of-day observations only
            # when those observations cover at least two distinct dates. Fine-grained
            # profile weights preserve peaks; hourly/weekly averages are fallback context.
            components = [(trained_prediction, 0.70)]
            if target_window_avg is not None:
                components.append((target_window_avg, 0.20))
            elif hourly_avg is not None:
                components.append((hourly_avg, 0.10))
            if weekly_window_avg is not None:
                components.append((weekly_window_avg, 0.10))
            elif weekly_avg is not None:
                components.append((weekly_avg, 0.10))
            predicted = sum(v*w for v,w in components) / sum(w for _,w in components)
            model_used=True
        else:
            components=[(trend,.5)]
            if target_window_avg is not None: components.append((target_window_avg,.3))
            elif hourly_avg is not None: components.append((hourly_avg,.2))
            if weekly_window_avg is not None: components.append((weekly_window_avg,.2))
            elif weekly_avg is not None: components.append((weekly_avg,.3))
            predicted=sum(v*w for v,w in components)/sum(w for _,w in components)
            metrics=cached["metrics"]

        usage=predicted/capacity*100; level="High" if usage>=85 else "Medium" if usage>=65 else "Low"
        explanations=[{"factor":"Forecast method","direction":"risk" if usage>=65 else "neutral",
                       "detail":(f"Trained Random Forest predicts {predicted:.3f} Mbps in {self.horizon_seconds//60} minutes." if model_used else "Model not ready; forecast uses short-term trend and repeated hourly/weekly averages.")},
                      {"factor":"Recent trend","direction":"risk" if slope>0.01 else "relief" if slope<-.01 else "neutral",
                       "detail":f"Recent throughput trend is {slope:+.5f} Mbps/second; trend-only forecast is {trend:.3f} Mbps."}]
        if target_window_avg is not None: explanations.append({"factor":"Target-time pattern","direction":"risk" if target_window_avg/capacity*100>=65 else "neutral","detail":f"Mean throughput within ±7 minutes of the forecast target time is {target_window_avg:.3f} Mbps across {len(window_dates)} dates; this fine-grained profile is blended into the forecast."})
        if hourly_avg is not None: explanations.append({"factor":"Hourly pattern","direction":"risk" if hourly_avg/capacity*100>=65 else "neutral","detail":f"Mean throughput for {h:02d}:00 is {hourly_avg:.3f} Mbps across {len(hour_dates[h])} dates."})
        else: explanations.append({"factor":"Hourly pattern","direction":"neutral","detail":f"Insufficient repeated data for {h:02d}:00; hourly pattern not used in forecast."})
        if weekly_window_avg is not None: explanations.append({"factor":"Weekday target-time pattern","direction":"risk" if weekly_window_avg/capacity*100>=65 else "neutral","detail":f"Mean throughput near the forecast target time on {target_dt.strftime('%A')} is {weekly_window_avg:.3f} Mbps across {len(weekly_window_dates)} dates; this profile is blended into the forecast."})
        if weekly_avg is not None: explanations.append({"factor":"Weekly pattern","direction":"risk" if weekly_avg/capacity*100>=65 else "neutral","detail":f"Mean throughput for {target_dt.strftime('%A')} at {h:02d}:00 is {weekly_avg:.3f} Mbps across {len(weekly_dates[(wd,h)])} dates."})
        else: explanations.append({"factor":"Weekly pattern","direction":"neutral","detail":"Insufficient repeated observations for this weekday/hour."})
        explanations.extend(contributions)

        hourly_profile=[]
        for hour in range(24):
            vals=hourly.get(hour,[]); avg=mean(vals) if vals else None; pct=avg/capacity*100 if avg is not None else None
            hourly_profile.append({"hour":f"{hour:02d}:00","average_mbps":round(avg,4) if avg is not None else None,
                "days_observed":len(hour_dates[hour]),"average_usage_percent":round(pct,1) if pct is not None else None,
                "congestion_level":("High" if pct>=85 else "Medium" if pct>=65 else "Low") if pct is not None else "Unknown"})
        day_names=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        weekly_profile=[]
        for day in range(7):
            for hour in range(24):
                vals=weekly.get((day,hour),[]); avg=mean(vals) if vals else None
                pct=avg/capacity*100 if avg is not None else None
                weekly_profile.append({"day":day_names[day],"hour":f"{hour:02d}:00","average_mbps":round(avg,4) if avg is not None else None,
                    "dates_observed":len(weekly_dates[(day,hour)]),"average_usage_percent":round(pct,1) if pct is not None else None,
                    "congestion_level":("High" if pct>=85 else "Medium" if pct>=65 else "Low") if pct is not None else "Unknown"})
        peak_hours=sorted([{"hour":f"{hour:02d}:00","average_mbps":round(mean(vals),4),"average_usage_percent":round(mean(vals)/capacity*100,1),
                    "days_observed":len(hour_dates[hour]),"congestion_level":"High" if mean(vals)/capacity*100>=85 else "Medium" if mean(vals)/capacity*100>=65 else "Low"}
                    for hour,vals in hourly.items() if len(hour_dates[hour])>=2],key=lambda item:item["average_usage_percent"],reverse=True)[:5]
        # Store at most one forecast per minute so dashboard polling does not
        # create thousands of near-identical evaluation records.
        last_forecast = ForecastEvaluation.query.order_by(ForecastEvaluation.created_at.desc()).first()
        last_forecast_time = None
        if last_forecast:
            last_forecast_time = last_forecast.created_at.replace(tzinfo=timezone.utc) if last_forecast.created_at.tzinfo is None else last_forecast.created_at
        if last_forecast_time is None or (now - last_forecast_time).total_seconds() >= 60:
            db.session.add(ForecastEvaluation(created_at=now, target_at=now+timedelta(seconds=self.horizon_seconds),
                predicted_throughput_mbps=max(0.0, float(predicted)), method="RandomForest" if model_used else "Statistical fallback"))
            db.session.commit()
        evaluated = ForecastEvaluation.query.filter(ForecastEvaluation.absolute_error_mbps.isnot(None)).order_by(ForecastEvaluation.evaluated_at.desc()).limit(1000).all()
        evaluation = {"evaluated_forecasts": len(evaluated), "mae_mbps": round(mean([r.absolute_error_mbps for r in evaluated]), 4) if evaluated else None,
                      "note": "Computed from forecasts paired with later real snapshots; not synthetic validation."}
        return {"ready":True,"samples":len(history),"horizon_seconds":self.horizon_seconds,"predicted_throughput_mbps":round(predicted,4),
            "predicted_usage_percent":round(usage,1),"predicted_level":level,"model":metrics,"model_used":model_used,
            "method":"Random Forest + repeated target-time profile blend" if model_used else "Statistical fallback: trend + repeated target-time/hourly/weekly profiles",
            "trend":"increasing" if slope>.01 else "decreasing" if slope<-.01 else "stable","slope_mbps_per_second":round(slope,6),
            "hourly_profile":hourly_profile,"weekly_profile":weekly_profile,"peak_hours":peak_hours,
            "target_local_time":target_dt.isoformat(),"explanations":explanations,"live_evaluation":evaluation,
            "note":"Forecast uses stored snapshots, which can include synthetic test data if loaded. Model training requires at least 100 horizon-matched examples across 3 dates; validation MAE is chronological holdout error, not a guarantee of future accuracy. Trained forecasts blend the Random Forest with repeated fine-grained target-time profiles when at least two dates are available. Peak congestion level is estimated from forecast throughput divided by configured capacity."}

    def _not_ready(self, count, usage):
        return {"ready":False,"samples":count,"required_samples":5,"horizon_seconds":self.horizon_seconds,
            "predicted_throughput_mbps":None,"predicted_usage_percent":None,"predicted_level":"Collecting history",
            "method":"Collecting historical data","model":{"trained":False,"reason":"Not enough history yet."},
            "model_used":False,"hourly_profile":[],"weekly_profile":[],"peak_hours":[],"live_evaluation":{"evaluated_forecasts":0,"mae_mbps":None,"note":"Waiting for forecasts to reach their target time."},
            "explanations":[{"factor":"Historical learning","direction":"neutral","detail":f"Collected {count} snapshots. More data is required before forecasting."},
                {"factor":"Current utilization","direction":"neutral","detail":f"Current observed usage is {usage:.1f}% of configured capacity."}],
            "note":"Keep the application running to collect timestamped measurements. The trained forecast activates only after enough matched historical examples are available."}
