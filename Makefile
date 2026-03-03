run:
	python main.py

dev:
	pip install -r requirements.txt && python main.py

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f
