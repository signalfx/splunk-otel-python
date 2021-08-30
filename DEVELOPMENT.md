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

## Releasing

Assuming the latest version is 0.14.0 and you want to releaase 0.15.0,

1. Run `make prepare-release VERSION=0.15.0` 
   This will bump the version where neccesary, update the changelog and commit
   all the changes to a new branch with name `release/v0.15.0`.
2. Submit a GitHub PR for the new branch and merge it once it is approved.
3. Switch to the main branch and pull the newly merged changes. Make sure you have the same commit
   checked out that was auto-generated in step 1.
4. Tag the commit with the version number
   ```shell
   git tag -s v0.15.0
   ```
5. Push the new tag to bot GitHub and GitLab
   ```shell
   git push github v0.15.0
   git push gitlab v0.15.0
   ```
   This will kickoff a Gitlab release job which will publish packages to pypi.org
   and create a new GitHub release.
6. You should review the GitHub release and add
   additional information to it if required.
