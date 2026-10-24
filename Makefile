PYTHON ?= .venv/bin/python
.PHONY: setup seed api web test build benchmark
setup:
	python3 -m venv .venv
	.venv/bin/pip install -r backend/requirements.lock
	npm ci --prefix frontend
seed:
	PYTHONPATH=backend $(PYTHON) -m app.seed
api:
	PYTHONPATH=backend $(PYTHON) -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
web:
	npm run dev --prefix frontend
test:
	$(PYTHON) -m pytest -q
build:
	npm run build --prefix frontend
benchmark:
	$(PYTHON) scripts/benchmark.py
