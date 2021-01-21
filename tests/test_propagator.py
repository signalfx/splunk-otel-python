import unittest

from opentelemetry.propagators import get_global_textmap
from opentelemetry.propagators.b3 import B3Format

from splunk_otel import tracing  # pylint:disable=C0415,W0611


class TestPropagator(unittest.TestCase):
    def test_splunk_otel_sets_b3_as_global_propagator(self):
        propagtor = get_global_textmap()
        self.assertIsInstance(propagtor, B3Format)
