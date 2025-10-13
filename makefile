# Root‑level Makefile helpers -------------------------------------
COMPOSE = docker compose
PROJECT = smart_scouting_app

SERVICES := api db redis web jupyter

.PHONY: up build stop down down-all restart prune clean

## Compile images if needed and bring up (recreate containers)
up: build
	$(COMPOSE) up -d --force-recreate --remove-orphans $(SERVICES)

## Explicit build (optional)
build:
	$(COMPOSE) build $(SERVICES)

## Build only DB + Redis
up-db:
	docker compose up -d db redis

## Manual ingestion targets 
ingest-full: up-db   ## Full bootstrap: players + history + ratings + news
	docker compose run --rm --build -t -e INGEST_MODE="" ingestion

ingest-players: up-db   ## Players-only: players + history + ratings (no news)
	docker compose run --rm --build -t -e INGEST_MODE="players" ingestion

ingest-news: up-db   ## News-only: scrape & embed NEW football news
	docker compose run --rm -t -e INGEST_MODE="news" ingestion

## Stop containers (NO delete networks nor volumes)
stop:
	$(COMPOSE) stop $(SERVICES)

## Delete containers and the network; KEEP volumes
down:
	$(COMPOSE) down --remove-orphans
	-$(COMPOSE) rm -fv $(SERVICES) 2>NUL
	-@docker network rm $(PROJECT_NAME)_scouting-net 2>NUL || echo Net cleared

## “all-zero” version (includes volumes) → use it only if you agree to delete pgdata
down-all:
	$(COMPOSE) down --volumes --remove-orphans
	-@docker network rm $(PROJECT_NAME)_scouting-net 2>NUL || echo Net cleared

## Quick restart
restart: down up                     # or  stop && up  if you don't want to recreate

## Aggressive cleanup of everything orphan (images, builds, etc.)
prune:
	docker container prune -f
	docker network   prune -f
	docker volume    prune -f
	docker buildx    prune -af

## “clean” = prune + build fresh version
clean: prune build