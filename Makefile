# Memaix — bekvämlighetskommandon

.PHONY: install up down seed logs

init:                  ## Front-dörren: ≤3 frågor → genererar all config + hemligheter, seedar demo
	python3 scripts/bootstrap.py --init

install:               ## Automatisk installation + Nextcloud-provisionering + vault-seed
	@command -v python3 >/dev/null || { echo "python3 krävs"; exit 1; }
	python3 scripts/bootstrap.py --tunnel

install-no-nextcloud:  ## Som install men utan medföljande Nextcloud (egen backend)
	python3 scripts/bootstrap.py --tunnel --no-nextcloud

trial:                 ## Tier 0: lokal utvärdering — stdio-MCP, inget tunnel/OAuth/domän
	python3 scripts/bootstrap.py --trial --no-nextcloud

go-remote:             ## Uppgradera en trial till mobil/multi-user (tunnel + Hydra OAuth)
	python3 scripts/bootstrap.py --tunnel

up:                    ## Starta containrar
	docker compose --profile tunnel --profile nextcloud up -d

down:                  ## Stoppa containrar
	docker compose down

seed:                  ## Bara seed-vaults (om de saknas)
	python3 -c "from scripts.bootstrap import load_acl, seed_vaults; seed_vaults(load_acl())"

logs:                  ## Följ gateway-loggar
	docker compose logs -f gateway

docs-check:            ## Flagga om något docs/*.md saknas i INDEX.md
	python3 scripts/check-docs-index.py
