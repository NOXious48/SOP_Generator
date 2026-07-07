# ProcessIQ dev commands. On Windows use: make <target> (via Git Bash / make) or run the commands.
.PHONY: install dev demo test lint up down fmt

install:
	python -m pip install -r requirements.txt

dev:
	uvicorn apps.api.main:app --reload --port 8000

demo:
	python -m scripts.demo_pipeline

test:
	pytest

lint:
	ruff check .

fmt:
	ruff check --fix .

up:
	docker compose up -d

down:
	docker compose down
