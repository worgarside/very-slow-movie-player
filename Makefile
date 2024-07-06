include .env
export

clean:
	sudo rm -rf .venv

create:
	virtualenv -p 3.12 .venv
	$(MAKE) install-all

disable:
	sudo systemctl disable vsmp.service

enable:
	sudo systemctl enable vsmp.service

install-python:
	.venv/bin/pip install -r requirements.txt

install-service:
	sudo cp service/vsmp.service /etc/systemd/system/
	sudo systemctl daemon-reload

install-all:
	@$(MAKE) install-python
	@$(MAKE) install-service

reset:
	git add .
	git stash save "Stash before update @ $(shell date)"
	git checkout main

restart:
	sudo systemctl restart vsmp.service

run:
	.venv/bin/python very_slow_movie_player/main.py

start:
	sudo systemctl start vsmp.service

stop:
	sudo systemctl stop vsmp.service

tail:
	clear && sudo journalctl -u vsmp.service -f -n 50

update:
	git add .
	git stash save "Stash before update @ $(shell date)"
	git pull --prune
	@$(MAKE) install-all
