# Development

## Bootstraping

### Install Poetry

This project uses poetry to manage dependencies and the package. Follow the
instructions here to install Poetry on your system:
https://python-poetry.org/docs/#installation

### Install dependencies

Once poetry is installed and available run the following command to install all
package required for local development.

```
make deps
```

## Testing in a local project

In order to install and test the package in a local test project, we'll need to
generate a setup.py file and then install an editable version of the package in
the test project's environment. Assuming the test project environment lives at
`/path/to/test/project/venv`, the following steps will install an editable
version of package in the test project.

```
make develop DEV_ENV=/path/to/test/project/venv
```

This will install an editable version of the package in the test project. Any
changes made to the library will automatically reflect in the test project
without the need to install the package again.
