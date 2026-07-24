# Local development helpers. Run `make help` for the list.
DEV := docker compose -f docker-compose.dev.yml

.PHONY: help dev-up dev-up-build dev-down dev-logs dev-ps dev-restart dev-psql headers

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

dev-up: ## Start the local stack (db + all apps, hot-reload)
	$(DEV) up -d

dev-up-build: ## Rebuild images then start (use after changing requirements.txt/Dockerfile)
	$(DEV) up -d --build

dev-down: ## Stop the stack (keeps the db volume)
	$(DEV) down

dev-logs: ## Tail logs from all services
	$(DEV) logs -f

dev-ps: ## Show running services
	$(DEV) ps

dev-restart: ## Restart all app containers
	$(DEV) restart

dev-psql: ## Open a psql shell on the dev database
	$(DEV) exec db psql -U $${POSTGRES_USER:-backend_user} -d $${POSTGRES_DB:-backend_db}

headers: ## Curl security headers from each running app
	@for p in 5001 5002 5004 5005; do \
		echo "--- localhost:$$p ---"; \
		curl -s -D - -o /dev/null http://localhost:$$p/ 2>/dev/null | \
		grep -iE 'content-security-policy|x-frame-options|x-content-type-options|strict-transport-security|cache-control' || echo "  (no response)"; \
	done
