import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import requests
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from prometheus_client import start_http_server, Gauge

# ---------------------------
# Env config
# ---------------------------
NAMESPACE = os.getenv("PINT_NAMESPACE", "platform-intelligence")

CRD_GROUP = os.getenv("PINT_CRD_GROUP", "platformintel.example.com")
CRD_VERSION = os.getenv("PINT_CRD_VERSION", "v1alpha1")
CRD_PLURAL = os.getenv("PINT_CRD_PLURAL", "platformhealthchecks")

PROM_URL = os.getenv("PROM_URL", "http://prom-prometheus-server.monitoring.svc:80")
CHECK_INTERVAL_SEC = int(os.getenv("CHECK_INTERVAL_SEC", "60"))

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

DEFAULT_WARN_HOURS = float(os.getenv("DEFAULT_WARN_HOURS", "4.0"))
DEFAULT_THRESHOLD_AVAILABLE_RATIO = float(os.getenv("DEFAULT_THRESHOLD_AVAILABLE_RATIO", "0.10"))
DEFAULT_WINDOW_MINUTES = int(os.getenv("DEFAULT_WINDOW_MINUTES", "45"))
DEFAULT_STEP_SECONDS = int(os.getenv("DEFAULT_STEP_SECONDS", "60"))

# Confidence bands (can be overridden via env if you want)
AUTO_CONFIDENCE = float(os.getenv("AUTO_CONFIDENCE", "0.90"))
APPROVAL_CONFIDENCE = float(os.getenv("APPROVAL_CONFIDENCE", "0.70"))

# ---------------------------
# Operator self-metrics
# ---------------------------
g_predictions = Gauge("pint_predictions_total", "Total predictions emitted", ["type"])
g_actions = Gauge("pint_action_recommendations_total", "Recommendations by tier", ["tier"])
g_last_slope = Gauge("pint_node_mem_available_slope_bytes_per_sec", "MemAvailable slope", ["node"])
g_ttf = Gauge("pint_node_time_to_threshold_seconds", "Estimated time-to-threshold seconds", ["node"])
g_conf = Gauge("pint_node_confidence", "Confidence score (0-1)", ["node"])


def log(msg: str):
    print(f"[{datetime.now(timezone.utc).isoformat()}] {msg}", flush=True)


def slack_post(text: str):
    if not SLACK_WEBHOOK_URL:
        return
    try:
        requests.post(SLACK_WEBHOOK_URL, json={"text": text}, timeout=10)
    except Exception as e:
        log(f"Slack post failed: {e}")


def prom_query_range(query: str, start_ts: float, end_ts: float, step: int):
    r = requests.get(
        f"{PROM_URL}/api/v1/query_range",
        params={"query": query, "start": start_ts, "end": end_ts, "step": step},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {data}")
    return data["data"]["result"]


def linear_slope(xs: List[float], ys: List[float]) -> float:
    """Simple least-squares slope dy/dx."""
    n = len(xs)
    if n < 2:
        return 0.0
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    denom = sum((x - x_mean) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    numer = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    return numer / denom


def confidence_from_ttf(ttf_hours: float, warn_hours: float) -> float:
    """
    Map time-to-threshold to a confidence score [0,1].
    - If ttf <= 0h: 1.0
    - If ttf >= warn_hours: 0.0
    - Linear in between (shorter ttf => higher confidence)
    """
    if warn_hours <= 0:
        return 0.0
    if ttf_hours <= 0:
        return 1.0
    if ttf_hours >= warn_hours:
        return 0.0
    # Closer => higher confidence
    return max(0.0, min(1.0, 1.0 - (ttf_hours / warn_hours)))


def tier_from_conf(conf: float) -> Tuple[str, str]:
    """
    This operator is intentionally observe-only.

    Confidence is reported as context, but it never authorizes or recommends
    an automated or approval-gated remediation action. Any remediation must
    be designed and reviewed as a separate, explicitly scoped capability.
    """
    return ("OBSERVE", "Observe only; investigate the signal manually.")


def emit_event(core: client.CoreV1Api, kind: str, name: str, reason: str, message: str, etype: str = "Warning"):
    """
    Create a Kubernetes Event in the operator namespace.

    NOTE (Kubernetes 1.35+):
    Event validation requires involvedObject.namespace to match event.namespace,
    even if the involved object is cluster-scoped (like Node).
    """
    now = datetime.now(timezone.utc).isoformat()

    event_body = {
        "apiVersion": "v1",
        "kind": "Event",
        "metadata": {
            "generateName": "platform-intel-",
            "namespace": NAMESPACE,
        },
        "type": etype,
        "reason": reason,
        "message": message,
        "firstTimestamp": now,
        "lastTimestamp": now,
        "count": 1,
        "involvedObject": {
            "kind": kind,
            "name": name,
            "namespace": NAMESPACE,
        },
        "source": {
            "component": "platform-intelligence-operator",
        },
    }

    try:
        core.create_namespaced_event(namespace=NAMESPACE, body=event_body)
    except ApiException as e:
        log(f"Failed to create event: {e}")


def load_kube():
    try:
        config.load_incluster_config()
        log("Loaded in-cluster Kubernetes config")
    except Exception:
        config.load_kube_config()
        log("Loaded local kubeconfig (dev mode)")


def get_phc_spec(custom: client.CustomObjectsApi) -> Dict:
    """MVP: read first PlatformHealthCheck in namespace."""
    try:
        obj = custom.list_namespaced_custom_object(
            group=CRD_GROUP,
            version=CRD_VERSION,
            namespace=NAMESPACE,
            plural=CRD_PLURAL,
        )
        items = obj.get("items", [])
        if not items:
            return {}
        return items[0].get("spec", {}) or {}
    except ApiException as e:
        log(f"Failed to list PlatformHealthCheck: {e}")
        return {}


def main():
    load_kube()
    core = client.CoreV1Api()
    custom = client.CustomObjectsApi()

    start_http_server(8000)
    log("Operator metrics on :8000/metrics")

    while True:
        try:
            spec = get_phc_spec(custom)

            window_minutes = int(spec.get("windowMinutes", DEFAULT_WINDOW_MINUTES))
            step_seconds = int(spec.get("stepSeconds", DEFAULT_STEP_SECONDS))
            warn_hours = float(spec.get("warnHours", DEFAULT_WARN_HOURS))
            threshold_ratio = float(spec.get("thresholdAvailableRatio", DEFAULT_THRESHOLD_AVAILABLE_RATIO))

            end_ts = time.time()
            start_ts = end_ts - window_minutes * 60

            q_avail = 'node_memory_MemAvailable_bytes'
            q_total = 'node_memory_MemTotal_bytes'

            avail_series = prom_query_range(q_avail, start_ts, end_ts, step_seconds)
            total_series = prom_query_range(q_total, start_ts, end_ts, step_seconds)

            total_latest: Dict[str, float] = {}
            for s in total_series:
                metric = s.get("metric", {})
                node = metric.get("node") or metric.get("instance") or "unknown"
                vals = s.get("values", [])
                if vals:
                    total_latest[node] = float(vals[-1][1])

            for s in avail_series:
                metric = s.get("metric", {})
                node = metric.get("node") or metric.get("instance") or "unknown"
                vals = s.get("values", [])
                if len(vals) < 5:
                    continue

                xs = [float(t) for t, _ in vals]
                ys = [float(v) for _, v in vals]

                slope = linear_slope(xs, ys)  # bytes/sec
                g_last_slope.labels(node=node).set(slope)

                total = total_latest.get(node)
                if not total:
                    continue

                if slope >= 0:
                    g_ttf.labels(node=node).set(float("inf"))
                    g_conf.labels(node=node).set(0.0)
                    continue

                current_avail = ys[-1]
                threshold = total * threshold_ratio
                remaining = current_avail - threshold

                ttf_sec = remaining / (-slope) if remaining > 0 else 0.0
                g_ttf.labels(node=node).set(ttf_sec)

                ttf_hours = ttf_sec / 3600.0
                conf = confidence_from_ttf(ttf_hours, warn_hours)
                g_conf.labels(node=node).set(conf)

                if ttf_hours <= warn_hours:
                    tier, rec = tier_from_conf(conf)
                    g_predictions.labels(type="node_mem_pressure").inc()
                    g_actions.labels(tier=tier).inc()

                    msg = (
                        f"[{tier}] Prediction: node '{node}' low MemAvailable in ~{ttf_hours:.2f}h "
                        f"(confidence={conf*100:.0f}%). "
                        f"avail={current_avail/1e9:.2f}GB, threshold={threshold/1e9:.2f}GB, "
                        f"slope={slope/1e6:.2f}MB/s, window={window_minutes}m. "
                        f"Recommendation: {rec}"
                    )

                    log(msg)

                    emit_event(
                        core=core,
                        kind="Node",
                        name=node,
                        reason="PredictedMemoryPressure",
                        message=msg,
                        etype="Warning",
                    )

                    # Keep this operator observe-only; no action-triggering
                    # notifications are sent from confidence tiers.

        except Exception as e:
            log(f"loop error: {e}")

        time.sleep(CHECK_INTERVAL_SEC)


if __name__ == "__main__":
    log("starting platform-intelligence operator")
    main()
