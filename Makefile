.PHONY: dev test lint pipeline-run eval-report

dev:
	docker compose up --build

test:
	docker compose run --rm --build backend python -m unittest discover -s tests

lint:
	docker compose run --rm --build backend python -m compileall -q .
	docker compose run --rm --build frontend npm run build

pipeline-run:
	docker compose run --rm --build backend python -m pipeline

eval-report:
	docker compose run --rm backend python -m models.evaluate
