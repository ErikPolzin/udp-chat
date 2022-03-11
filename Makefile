### Makefile for seting up the virtual enviroment ###

### Create virtual enviroment ###

venv:
	python3 -m venv venv
	pip install -e .

clean:
	rm -rf venv