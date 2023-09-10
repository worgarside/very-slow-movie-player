create-env:
	virtualenv -p 3.11 .venv
	.venv/bin/pip install -r requirements.txt
