> The official Splunk documentation for this page is [Troubleshoot Python instrumentation](https://docs.signalfx.com/en/observability/gdi/get-data-in/application/python/troubleshooting/common-python-troubleshooting.html).

# Troubleshooting

- Depending on the default python version on your system, you might want to use
  `pip3` and `python3` instead.
- To be able to run `splunk-py-trace` and `splunk-py-trace-bootstrap`, the
  directory pip installs scripts to will have to be on your system's PATH
  environment variable. Generally, this works out of the box when using virtual
  environments, installing packages system-wide or in container images. In some
  cases, pip may install packages into your user local environment. In that
  case you'll need to add your Python user base's bin directory to your system
  path. You can find out your Python user base as follows by running `python -m
  site --user-base`.

  For example, if `python -m site --user-base` reports that
  `/Users/splunk/.local` as the Python user base, then you can add the
  directory to your path on Unix like system as follows:

  ```
  export PATH="/Users/splunk/.local/bin:$PATH"
  ```
- Enable debug logging like you would for any Python application.

  ```python
  import logging

  logging.basicConfig(level=logging.DEBUG)
  ```

  > :warning: Debug logging is extremely verbose and resource intensive. Enable
  > debug logging only when needed and disable when done.
