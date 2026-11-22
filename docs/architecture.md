# Architecture

The operator is an observe-only signal pipeline. It estimates a trend from Prometheus metrics and reports a Kubernetes Warning Event; it does not remediate nodes or workloads.

~~~mermaid
flowchart TD
  C[PlatformHealthCheck custom resource] --> O[Platform Intelligence operator]
  O -->|query_range| P[Prometheus]
  P -->|MemAvailable and MemTotal samples| O
  O --> W[Rolling observation window]
  W --> R[Linear regression slope]
  R --> T[Time-to-threshold estimate]
  T --> F[Confidence calculation]
  F --> S[OBSERVE-only recommendation]
  S --> E[Kubernetes Warning Event]
  O --> M[Prometheus operator metrics]
  E --> U[Platform engineer investigates]
~~~

## Runtime boundaries

- The custom resource supplies the observation window, query step, warning horizon and available-memory threshold.
- The operator queries node_memory_MemAvailable_bytes and node_memory_MemTotal_bytes.
- A least-squares slope estimates time to the configured threshold.
- Confidence is contextual information only. tier_from_conf always returns OBSERVE.
- The operator emits a Warning Event and exposes metrics; no automated action is performed.

## Repository evidence

- Operator logic: operator/app/main.py
- Unit tests: operator/tests/test_prediction_logic.py
- CRD and Helm resources: charts/k8s-platform-intelligence/
- CI: .github/workflows/ci.yml
