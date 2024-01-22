all: venv install

.PHONY: venv
venv:
	python -m venv venv

.PHONY: install
install:
	./venv/bin/pip install -r requirements.txt
	./venv/bin/splunk-py-trace-bootstrap

.PHONY: run
run:
	./venv/bin/splunk-py-trace python main.py
