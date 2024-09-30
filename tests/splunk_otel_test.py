from splunk_otel import __about__


def test_version():
    assert __about__.__version__ == '2.0.0a1'
