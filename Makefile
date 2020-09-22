
.PHONY: clean 
clean:
	rm dist/*


.PHONY: build
build: clean
	python setup.py sdist


.PHONY: publish
publish: clean build 
	twine upload dist/splunk-opentelemetry-*.tar.gz
