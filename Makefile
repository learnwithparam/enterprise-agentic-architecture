.PHONY: up down provision test evals record serve web walkthrough check lab

up:            ## start Floci (local AWS) and provision every resource
	docker compose up -d
	@for i in $$(seq 1 60); do curl -sf -o /dev/null localhost:4566 && break; sleep 1; done
	uv run python -m hcpagents.infra

down:
	docker compose down

provision:     ## wipe state and reseed; the locked archive keeps old chains
	uv run python -m hcpagents.infra --reset

test:
	uv run pytest -q

evals:         ## run every inquiry through the graph and apply evals/gate.toml (replay, free)
	uv run python -m hcpagents.evals

record:        ## call claude-haiku-5-5 for every inquiry and rewrite recordings (about $0.02)
	LIVE=1 uv run python -m hcpagents run all

serve: web     ## console on http://localhost:8765
	uv run uvicorn hcpagents.api:app --port 8765

web:
	cd web && npm ci --silent && npm run build --silent

walkthrough: up  ## recapture docs/product-walkthrough-shots from a fresh replay run
	scripts/walkthrough.sh

lab:           ## make lab N=<lab-folder>: run one lab's tests
	uv run pytest -q labs/$(N)

check: up      ## the gate: tests, evals, mutants, prose, web build, mermaid
	uv run pytest -q
	uv run python -m hcpagents.evals
	uv run python scripts/mutate.py
	uv run python scripts/check_prose.py
	$(MAKE) web
	cd web && npx playwright-core install --only-shell --no-remove chromium > /dev/null
	node web/scripts/check-mermaid.mjs
