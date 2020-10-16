DEV_VENV?=""

.PHONY: deps
deps:
	poetry install

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
