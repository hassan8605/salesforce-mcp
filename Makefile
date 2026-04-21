.PHONY: up down build restart logs shell ps clean dev sync

## Build the Docker image
build:
	docker compose build

## Start the container (build if needed)
up:
	docker compose up -d --build

## Stop and remove containers
down:
	docker compose down

## Restart the container
restart:
	docker compose restart salesforce-mcp

## Stream container logs
logs:
	docker compose logs -f salesforce-mcp

## Open a shell inside the running container
shell:
	docker compose exec salesforce-mcp /bin/bash

## Show running containers
ps:
	docker compose ps

## Stop containers and remove volumes
clean:
	docker compose down -v

## Run locally with uv (auto-reload)
dev:
	uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload

## Install / sync dependencies
sync:
	uv sync
