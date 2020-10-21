import unittest
from unittest import mock
from urllib.parse import ParseResult

from splunk_otel.tracing import parse_jaeger_url


class TestInitialization(unittest.TestCase):
    def test_parse_jaeger_url(self):
        urls = {
            "": True,
            "example.com": True,
            "localhost:8888": True,
            "localhost:8888/path": True,
            "http://localhost:8888": True,
            "http://localhost:8888/path": False,
        }

        for url, raises in urls.items():
            if raises:
                with self.assertRaises(ValueError):
                    parse_jaeger_url(url)
            else:
                parsed = parse_jaeger_url(url)
                self.assertIsInstance(parsed, ParseResult)
                self.assertEqual(parsed.geturl(), url)
