.PHONY: test-unit test-integration test up down clean

test-unit:
	@echo "Running unit tests..."
	python -m pytest tests/ -v

test-integration:
	@echo "Bringing up the mesh in background for integration tests..."
	docker compose up -d
	@echo "Running integration tests..."
	python -m pytest tests/ -v
	@echo "Tearing down the mesh..."
	docker compose down

test: test-unit test-integration

up:
	@echo "Starting the CivicMesh local environment..."
	docker compose up --build

down:
	@echo "Stopping and cleaning up the CivicMesh local environment..."
	docker compose down -v

clean:
	@echo "Cleaning up dangling images and stopped containers..."
	docker system prune -f
