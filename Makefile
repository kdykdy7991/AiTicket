.PHONY: backend frontend

backend:
	docker compose -f backend/docker-compose.yml build api
	docker compose -f backend/docker-compose.yml up -d db redis
	docker compose -f backend/docker-compose.yml run --rm api alembic upgrade head
	docker compose -f backend/docker-compose.yml run --rm api python scripts/seed.py --phase9
	docker compose -f backend/docker-compose.yml up api

frontend:
	cd frontend && npm run dev
