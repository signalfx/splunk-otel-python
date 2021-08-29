DEV_VENV?=""
VERSION?=""

.PHONY: deps
deps:
	poetry install --extras all

.PHONY: clean
clean:
	@rm -rf dist
	@rm -rf dev
	@rm -rf splunk_opentelemetry.egg-info

.PHONY: develop
develop:
ifeq ($(DEV_VENV),"")
	@echo "Usage: make develop DEV_ENV=~/path/to/dev/project/venv"
else
	$(DEV_VENV)/bin/pip uninstall splunk-opentelemetry --yes
	. $(DEV_VENV)/bin/activate && poetry install --no-dev --extras all
endif

.PHONY: build
build:
	poetry build

.PHONY: publish
publish:
	poetry publish --build

.PHONY: isort-check
isort-check:
	poetry run isort --profile black --diff --check-only ./splunk_otel ./tests

.PHONY: black-check
black-check:
	poetry run black --diff --check ./splunk_otel ./tests/

.PHONY: pylint
pylint:
	poetry run pylint ./splunk_otel ./tests/ ./scripts/

.PHONY: flake8 
flake8:
	poetry run flake8 ./splunk_otel ./tests/ ./scripts/

.PHONY: lint
lint: isort-check black-check flake8 pylint

.PHONY: mypy
mypy:
	poetry run mypy --namespace-packages --show-error-codes splunk_otel/

.PHONY: fmt
fmt: isort black

.PHONY: black
black:
	poetry run black splunk_otel tests scripts

.PHONY: isort
isort:
	poetry run isort --profile black ./splunk_otel ./tests ./scripts

.PHONY: test
test:
	poetry run pytest tests/unit

.PHONY: integration
integration:
	poetry run pytest tests/integration

.PHONY: test-with-cov
test-with-cov:
	poetry run coverage erase
	poetry run pytest --cov splunk_otel --cov-append --cov-branch --cov-report='' --junit-xml=test_results/results.xml tests/unit/
	poetry run coverage report --show-missing
	poetry run coverage xml

.PHONY: create-github-release
ci-create-github-release:
	poetry run python scripts/create_gh_release.py --dry-run=false

.PHONY: prepare-release
prepare-release:
ifeq ($(VERSION),"")
	@echo "Usage: make prepare-release VERSION=<version_number>"
else
	git checkout -B release/v$(VERSION)
	python scripts/prepare_release.py --version $(VERSION)
	git add -A .
	git commit -m"Preparing release v$(VERSION)"
endif
