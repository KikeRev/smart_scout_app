# Root‑level Makefile helpers -------------------------------------
COMPOSE = docker compose
PROJECT = smart_scouting_app

SERVICES := api dashboard ingestion db redis web jupyter

.PHONY: up build stop down down-all restart prune clean

## Compila imágenes si hace falta y levanta (recrea contenedores)
up: build
	$(COMPOSE) up -d --force-recreate --remove-orphans $(SERVICES)

## Build explícito (opcional)
build:
	$(COMPOSE) build $(SERVICES)

## Detiene contenedores (NO borra redes ni volúmenes)
stop:
	$(COMPOSE) stop $(SERVICES)

## Elimina contenedores y la red; CONSERVA volúmenes
down:
	$(COMPOSE) down --remove-orphans
	-$(COMPOSE) rm -fv $(SERVICES) 2>NUL
	-@docker network rm $(PROJECT_NAME)_scouting-net 2>NUL || echo Net cleared

## Versión “todo-a-cero” (incluye volúmenes) → úsala sólo si estás de acuerdo en borrar pgdata
down-all:
	$(COMPOSE) down --volumes --remove-orphans
	-@docker network rm $(PROJECT_NAME)_scouting-net 2>NUL || echo Net cleared

## Reinicia rápido
restart: down up                     # o  stop && up  si no quieres recrear

## Limpieza agresiva de todo lo huérfano (imágenes, builds, etc.)
prune:
	docker container prune -f
	docker network   prune -f
	docker volume    prune -f
	docker buildx    prune -af

## “clean” = prune + build fresco
clean: prune build