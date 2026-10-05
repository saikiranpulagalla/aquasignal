.PHONY: test test-aqua test-core run aqua-benchmark aqua-holdout-verify signallock-benchmark release-gate wheel

test:
	pytest -q

test-aqua:
	pytest -q tests/aqua

test-core:
	pytest -q tests/unit tests/integration tests/regression

run:
	python -m apps.aqua_api

aqua-benchmark:
	python scripts/run_aqua_benchmark.py

aqua-holdout-verify:
	python scripts/verify_aqua_holdout.py

signallock-benchmark:
	python scripts/run_benchmark.py

release-gate:
	python scripts/release_gate.py

wheel:
	rm -rf build dist aquasignal_oneaquahealth.egg-info
	python scripts/sync_package_resources.py
	python -m pip wheel . --no-deps --no-build-isolation -w dist
