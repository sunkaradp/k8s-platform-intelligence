# Verification and evidence

## Automated checks

The repository CI workflow installs operator/requirements.txt and runs Python unittest discovery against operator/tests.

The current test module contains eight test cases covering:

- Linear slope calculation and insufficient/identical timestamp inputs.
- Confidence behavior at, below and within the warning horizon.
- Non-positive warning horizon handling.
- A guard verifying every confidence tier remains OBSERVE and never recommends node cordon/drain.

Sources: .github/workflows/ci.yml and operator/tests/test_prediction_logic.py.

## Implemented behavior

- Prometheus range queries for available and total node memory.
- Rolling-window linear regression and time-to-threshold estimate.
- Confidence calculation and operator self-metrics.
- Kubernetes Warning Event emission.
- Custom Resource configuration and Helm deployment resources.
- Observe-only behavior enforced in the recommendation function.

## Not yet claimed as measured

The repository does not publish a benchmark dataset, prediction accuracy, false-positive rate, warning lead-time distribution, or multi-node cluster performance results. The illustrative event in the README is not a benchmark or service-level guarantee.

## Reproduce the unit tests

~~~bash
cd operator
pip install -r requirements.txt
python -m unittest discover -s tests -v
~~~

## Next evidence to collect

1. Run against a disposable multi-node cluster with Prometheus.
2. Capture timestamped metric windows and emitted Warning Events.
3. Compare predicted threshold crossings with observed node memory.
4. Report false positives, missed warnings and lead time across repeated scenarios.
5. Keep the operator observe-only while collecting and reviewing these results.
