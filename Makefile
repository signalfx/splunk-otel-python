DEV_VENV?=""

.PHONY: deps
deps:
	poetry install --no-root

.PHONY: clean
clean:
	@rm -rf dist
	@rm -rf dev
	@rm -rf splunk_opentelemetry.egg-info

.PHONY: develop
develop: clean
	@mkdir -p dev
	@ln -s $(PWD)/splunk_otel dev/
	@poetry run dephell deps convert
	@mv setup.py dev/
	@echo $(DEV_VENV)
ifeq ($(DEV_VENV),"")
	@echo "Prepared dev directory. Activate the target virtual env and run _python setup.py develop_ from within the dev directory."
	@echo "Example:\n\n\tcd dev\n\t~/path/to/venv/bin/python setup.py develop\n"
else
	cd dev; pip uninstall splunk-opentelemetry; $(DEV_VENV)/bin/python setup.py develop
endif

.PHONY: build
build:
	poetry build

.PHONY: publish
publish:
	poetry publish

.PHONY: lint 
lint:
	@echo "faking lint"

.PHONY: fmt
fmt: isort black

.PHONY: black
black:
	poetry run black splunk_otel tests

.PHONY: isort
isort:
	poetry run isort --profile black splunk_otel tests

.PHONY: test
test:
	poetry run pytest tests/

.PHONY: test-with-cov
test-with-cov:
	poetry run coverage erase
	poetry run pytest --cov splunk_otel --cov-append --cov-branch --cov-report='' tests/
	poetry run coverage report --show-missing
	poetry run coverage xml