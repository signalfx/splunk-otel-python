
.PHONY: clean 
clean:
	rm dist/*

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