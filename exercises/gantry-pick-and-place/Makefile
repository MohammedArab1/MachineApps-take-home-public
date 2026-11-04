.PHONY: install backend frontend backend-test frontend-test test lint build up down

install:
	cd backend && python3.10 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
	cd frontend && npm install

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

backend-test:
	cd backend && .venv/bin/pytest --cov=app --cov-report=term-missing

frontend-test:
	cd frontend && npm run test:coverage

test: backend-test frontend-test

lint:
	cd backend && .venv/bin/ruff check app tests
	cd frontend && npm run lint && npm run typecheck

build:
	cd frontend && npm run build

up:
	docker compose up --build

down:
	docker compose down
