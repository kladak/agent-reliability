.PHONY: install test eval-offline eval-compare

install:
	python -m pip install -e ".[dev]"

test:
	python -m pytest -q

eval-offline:
	python -m agent_reliability.eval.runner --offline --report reports/latest-offline.json

eval-compare:
	python -m agent_reliability.eval.runner --compare reports/baseline-offline.json reports/latest-offline.json
