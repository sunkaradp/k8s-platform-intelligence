# k8s-platform-intelligence

Small experiment with a Kubernetes operator that tries to predict node memory pressure before pods start getting evicted.

Why

Most of the time, you only notice memory pressure when the node flips to MemoryPressure and pods start getting evicted.

By then, you’re already reacting.

I wanted to see if it’s possible to detect the trend earlier by looking at Prometheus metrics instead of waiting for the condition to trigger.

This is not production-ready. It’s mainly a learning project around the Kubernetes Operator pattern and building simple predictive control loops inside a cluster.

What it does

The operator runs inside the cluster and continuously:

Queries Prometheus for:

node_memory_MemAvailable_bytes

node_memory_MemTotal_bytes

Calculates a regression slope over a rolling time window

Estimates when available memory will reach a configurable threshold

Converts that estimate into a confidence score

Emits a native Kubernetes Warning event:

PredictedMemoryPressure

It currently runs in “observe” mode — no automatic remediation.

Example Event
Warning  PredictedMemoryPressure  node/minikube
[OBSERVE] Prediction: node 'minikube' low MemAvailable in ~2.90h (confidence=28%).
Recommendation: Observe only (log + learn).
Configuration (CRD)

Example PlatformHealthCheck resource:

apiVersion: platformintel.example.com/v1alpha1
kind: PlatformHealthCheck
metadata:
  name: default
  namespace: platform-intelligence
spec:
  windowMinutes: 45
  stepSeconds: 60
  warnHours: 4
  thresholdAvailableRatio: 0.10

The operator reads this configuration dynamically.

How it works (high level)

Pull time-series memory data from Prometheus.

Fit a simple linear regression to estimate the memory consumption trend.

Calculate time-to-threshold based on current slope.

Convert time-to-threshold into a confidence score.

Emit a Kubernetes Event with a recommendation tier (OBSERVE, APPROVAL, AUTO).

No heavy ML yet — just basic regression and signal interpretation.

Current status

Tested on Minikube

Uses linear regression

Emits native Kubernetes events

Exposes Prometheus metrics from the operator

Configuration via CRD

I’ve broken this cluster more than once while testing this, which was honestly part of the learning process.

What I learned building this

Writing an operator is very different from writing a standalone script.

The Kubernetes Events API has sharp edges (especially with newer validation rules).

Time-series prediction is less about fancy models and more about clean signals.

Control loops are simple in theory but tricky in real cluster behavior.

Next steps

Replace regression with anomaly detection (e.g., Isolation Forest)

Add safe remediation logic with confidence gating

Improve signal filtering and reduce noise

Test in a multi-node cluster

This project started as curiosity about predictive signals in Kubernetes and turned into a deeper dive into how cluster control loops actually work.
