.PHONY: dev test lint pipeline-run eval-report

dev:
	docker compose up --build

test:  # separate database: tests insert and delete fixture rows
	docker compose up -d --wait postgres
	docker compose exec -T postgres sh -c "psql -U heatwave -d heatwave -tAc \"SELECT 1 FROM pg_database WHERE datname='heatwave_test'\" | grep -q 1 || createdb -U heatwave heatwave_test"
	docker compose run --rm --build -e DATABASE_URL=postgresql://heatwave@postgres:5432/heatwave_test backend python -m unittest discover -s tests

lint:
	docker compose run --rm --build backend python -m compileall -q .
	docker compose run --rm --build frontend npm run build

pipeline-run:
	docker compose run --rm --build backend python -m pipeline

eval-report:
	docker compose run --rm --build backend python -m models.report
