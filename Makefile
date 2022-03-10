### Makefile for seting up the virtual enviroment ###

### Create virtual enviroment ###

venv:
	python3 -m venv venv
	pip install -e .

server:
	python3 -m udp_chat.server

cli:
	python3 -m udp_chat.client

gui:
	python3 -m udp_chat.gui_client

clean:
	rm -rf venv