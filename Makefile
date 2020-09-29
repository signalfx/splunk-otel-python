.PHONY: deps 
deps:
	poetry install

.PHONY: clean 
clean:
	@rm -rf dist/*
	@rm -rf dev/*

.PHONY: develop 
develop: clean
	@mkdir -p dev
	@ln -s $(PWD)/splunk_otel dev/
	@poetry run dephell deps convert
	@mv setup.py dev/
	@echo "Prepared dev directory. Active the target virtual env and run _python setup.py develop_ from within the dev directory."

.PHONY: build
build:
	poetry build

.PHONY: publish
publish:
	poetry publish

.PHONY: fmt
fmt: isort black

.PHONY: black 
black:
	poetry run black splunk_otel

.PHONY: isort 
isort:
	poetry run isort --profile black splunk_otel

.PHONY: test
test:
	poetry run pytest tests/