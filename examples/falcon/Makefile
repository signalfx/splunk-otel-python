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
	OTEL_EXPORTER_JAEGER_ENDPOINT='http://localhost:14268/api/traces' ./venv/bin/splunk-py-trace python main.py	
