.PHONY: test-unit test-generators test-analytics test-network test-agents test-integration test demo-metrics frontend up down clean

test-unit:
	@echo "Running unit tests..."
	python -m pytest tests/ -v --ignore=tests/integration

test-generators:
	@echo "Running generator unit tests..."
	python -m pytest tests/generators/ -v

test-analytics:
	@echo "Running analytics unit tests..."
	python -m pytest tests/analytics/ -v

test-network:
	@echo "Running network transport unit tests..."
	python -m pytest tests/network/ -v

test-agents:
	@echo "Running AI agents tests..."
	python -m unittest discover -s scripts/agents/tests

test-integration:
	@echo "Running real network TCP integration tests..."
	python -m pytest tests/integration/ -v

test: test-unit test-agents test-integration

demo-metrics:
	@echo "Generating demo metrics fixtures..."
	python scripts/generate_demo_metrics.py

frontend:
	@echo "Launching CivicMesh Analytics Dashboard..."
	python -m streamlit run civicmesh/analytics/frontend.py

up:
	@echo "Starting the CivicMesh local environment..."
	docker compose up --build

down:
	@echo "Stopping and cleaning up the CivicMesh local environment..."
	docker compose down -v

clean:
	@echo "Cleaning up dangling images, stopped containers and caches..."
	docker system prune -f
	python -c "import pathlib, shutil; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__')]" 2>/dev/null || true
	python -c "import pathlib, shutil; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('.pytest_cache')]" 2>/dev/null || true
