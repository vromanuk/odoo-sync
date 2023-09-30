COMPOSE_PROJECT_NAME=odoo-sync
COMPOSE_FILE=docker/docker-compose.yml
include .env
export

run:
	uvicorn src.main:app --reload

fmt:
	black .
	ruff check --fix .

lint:
	black . --check
	ruff check .
	mypy src

install:
	pip-compile
	pip-sync

docker-up:
	docker-compose up --remove-orphans -d

docker-build:
	docker-compose build --no-cache