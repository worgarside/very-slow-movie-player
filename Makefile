create-env:
	virtualenv -p 3.11 .venv
	$(MAKE) install

install:
	.venv/bin/pip install -r requirements.txt

include .env
export

run:
	.venv/bin/python src/main.py
