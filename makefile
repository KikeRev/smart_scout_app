# Root‑level Makefile helpers -------------------------------------
COMPOSE = docker compose
PROJECT = smart_scouting_app

SERVICES := api db redis web jupyter ingestion
CORE_SERVICES := api web db redis jupyter

.PHONY: up build stop stop-core down down-all restart restart-fast prune clean \
        ps logs logs-api logs-web logs-db shell-api shell-web shell-db \
        up-db up-core ingest-full ingest-players ingest-news help

## Show available commands
help:
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

## Bring up services (uses existing images, fast)
up: 
	$(COMPOSE) up -d --remove-orphans $(SERVICES)

## Build images and bring up services (complete setup)
build:
	$(COMPOSE) build $(SERVICES)
	$(COMPOSE) up -d --force-recreate --remove-orphans $(SERVICES)

## Bring up core services only (api, web, db, redis)
up-core:
	$(COMPOSE) up -d --remove-orphans $(CORE_SERVICES)

## Build only DB + Redis
up-db:
	$(COMPOSE) up -d db redis

## Show container status
ps:
	$(COMPOSE) ps

## View logs (all services)
logs:
	$(COMPOSE) logs -f $(SERVICES)

## View API logs only
logs-api:
	$(COMPOSE) logs -f api

## View Web logs only
logs-web:
	$(COMPOSE) logs -f web

## View DB logs only
logs-db:
	$(COMPOSE) logs -f db

## Enter API container shell
shell-api:
	$(COMPOSE) exec api bash

## Enter Web container shell
shell-web:
	$(COMPOSE) exec web bash

## Enter DB shell (psql)
shell-db:
	$(COMPOSE) exec db psql -U scout -d scouting

## Manual ingestion targets 
ingest-full: up-db   ## Full bootstrap: players + history + ratings + news
	$(COMPOSE) run --rm -t -e INGEST_MODE="" ingestion

ingest-players: up-db   ## Players-only: players + history + ratings (no news)
	$(COMPOSE) run --rm -t -e INGEST_MODE="players" ingestion

ingest-news: up-db   ## News-only: scrape & embed NEW football news
	$(COMPOSE) run --rm -t -e INGEST_MODE="news" ingestion

## Stop containers (NO delete networks nor volumes)
stop:
	$(COMPOSE) stop $(SERVICES)

## Stop core services only (api, web, db, redis)
stop-core:
	$(COMPOSE) stop $(CORE_SERVICES)

## Delete containers and the network; KEEP volumes
down:
	$(COMPOSE) down --remove-orphans
	-$(COMPOSE) rm -fv $(SERVICES) 2>NUL
	-@docker network rm $(PROJECT)_scouting-net 2>NUL || echo Net cleared

## "all-zero" version (includes volumes) → use it only if you agree to delete pgdata
down-all:
	@echo "⚠️  WARNING: This will delete ALL data (database, volumes, etc.)"
	@echo "Press Ctrl+C to cancel or Enter to continue..."
	@read -r
	$(COMPOSE) down --volumes --remove-orphans
	-@docker network rm $(PROJECT)_scouting-net 2>NUL || echo Net cleared

## Quick restart (recreate)
restart: down up

## Fast restart (no recreate)
restart-fast: stop up

## Aggressive cleanup of everything orphan (images, builds, etc.)
prune:
	docker container prune -f
	docker network   prune -f
	docker volume    prune -f
	docker buildx    prune -af

## "clean" = down-all + build fresh version
clean: down-all build