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