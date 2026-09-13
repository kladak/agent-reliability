.PHONY: install test eval-offline

install:
	python -m pip install -e ".[dev]"

test:
	python -m pytest -q

eval-offline:
	python -m agent_reliability.eval.runner --offline --report reports/latest-offline.json
