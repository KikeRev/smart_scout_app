# Root‑level Makefile helpers -------------------------------------
COMPOSE = docker compose

.PHONY: build up dev down logs ps shell migrate test clean

build:
	$(COMPOSE) build  

up:
	$(COMPOSE) up -d api dashboard ingestion db redis web jupyter

dev:
	$(COMPOSE) --profile dev up -d web jupyter db redis

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100

ps:
	$(COMPOSE) ps

shell-dev:
	$(COMPOSE) exec jupyter web bash

shell-web:
	$(COMPOSE) exec web db redis bash

shell:
	$(COMPOSE) exec api bash

migrate:
	$(COMPOSE) exec dashboard python apps/dashboard/manage.py migrate

test:
	$(COMPOSE) exec api pytest -q

clean:
	$(COMPOSE) down -v --remove-orphans
	docker system prune -f