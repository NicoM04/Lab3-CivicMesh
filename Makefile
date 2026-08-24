.PHONY: test-unit test-generators test-agents test-integration test up down clean

test-unit:
	@echo "Running unit tests..."
	python -m pytest tests/ -v

test-generators:
	@echo "Running generator unit tests..."
	python -m pytest tests/generators/ -v

test-agents:
	@echo "Running AI agents tests..."
	python -m unittest discover -s scripts/agents/tests

test-integration:
	@echo "Running integration tests..."
	python -m pytest tests/ -k integration -v

test: test-unit test-agents test-integration

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
