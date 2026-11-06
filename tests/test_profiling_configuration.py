import pytest
from opentelemetry._logs import NoOpLoggerProvider
from opentelemetry.configuration import ConfigurationError
from opentelemetry.sdk.resources import Resource

from splunk_otel.env import Env
from splunk_otel.profile import start_continuous_profiling_from_environment
from splunk_otel.declarative_profiling import configure_declarative_continuous_profiling


@pytest.fixture
def profiling_contexts(monkeypatch):
    contexts = []

    class FakeProfilingContext:
        def __init__(self, resource, interval_millis, logger):
            self.resource = resource
            self.interval_millis = interval_millis
            self.logger = logger
            self.started = False
            contexts.append(self)

        def start(self):
            self.started = True

        def stop(self):
            self.started = False

    monkeypatch.setattr("splunk_otel.profile.ProfilingContext", FakeProfilingContext)

    def _fake_create_logger_provider(_config, _resource):
        return NoOpLoggerProvider()

    monkeypatch.setattr("splunk_otel.declarative_profiling.create_logger_provider", _fake_create_logger_provider)
    return contexts


@pytest.mark.parametrize(("cpu_profiler", "interval"), [({}, 1000), (None, 1000), ({"sampling_interval": 250}, 250)])
def test_yaml_starts_continuous_profiling(monkeypatch, profiling_contexts, cpu_profiler, interval):
    monkeypatch.setenv("SPLUNK_PROFILER_ENABLED", "false")
    monkeypatch.setenv("SPLUNK_PROFILER_CALL_STACK_INTERVAL", "9999")
    resource = Resource({"service.name": "yaml-service", "deployment.environment.name": "test"})

    configure_declarative_continuous_profiling(
        {"splunk": {"profiling": {"always_on": {"cpu_profiler": cpu_profiler}}}}, resource
    )

    (context,) = profiling_contexts
    assert context.started
    assert context.interval_millis == interval
    assert context.resource is resource


def test_environment_starts_continuous_profiling(profiling_contexts):
    environment = Env({"OTEL_SERVICE_NAME": "environment-service", "SPLUNK_PROFILER_CALL_STACK_INTERVAL": "250"})

    context = start_continuous_profiling_from_environment(environment)

    assert profiling_contexts == [context]
    assert context.started
    assert context.interval_millis == 250
    assert context.resource.attributes["service.name"] == "environment-service"


@pytest.mark.parametrize("configuration_source", ["environment", "declarative"])
def test_continuous_profiling_stops_at_exit(monkeypatch, profiling_contexts, configuration_source):
    shutdown_callbacks = []

    def _fake_register_shutdown(callback):
        shutdown_callbacks.append(callback)

    monkeypatch.setattr("splunk_otel.profile.atexit.register", _fake_register_shutdown)
    if configuration_source == "environment":
        start_continuous_profiling_from_environment(Env({"OTEL_SERVICE_NAME": "environment-service"}))
    else:
        configure_declarative_continuous_profiling(
            {"splunk": {"profiling": {"always_on": {"cpu_profiler": {}}}}}, Resource({})
        )

    (context,) = profiling_contexts
    assert context.started
    (shutdown,) = shutdown_callbacks
    shutdown()
    assert not context.started


@pytest.mark.parametrize(
    "distribution",
    [
        None,
        {},
        {"splunk": None},
        {"splunk": {"profiling": {}}},
        {"splunk": {"profiling": {"always_on": {}}}},
        {"splunk": {"profiling": {"callgraphs": {}}}},
    ],
)
def test_yaml_without_cpu_profiler_does_not_start_profiling(monkeypatch, profiling_contexts, distribution):
    monkeypatch.setenv("SPLUNK_PROFILER_ENABLED", "true")

    configure_declarative_continuous_profiling(distribution, Resource({}))

    assert not profiling_contexts


@pytest.mark.parametrize("interval", [0, -1, True, 1.5, "1000", None])
def test_invalid_sampling_interval_fails_before_starting(profiling_contexts, interval):
    with pytest.raises(ConfigurationError, match="sampling_interval must be a positive integer"):
        configure_declarative_continuous_profiling(
            {"splunk": {"profiling": {"always_on": {"cpu_profiler": {"sampling_interval": interval}}}}},
            Resource({}),
        )

    assert not profiling_contexts


@pytest.mark.parametrize("key", ["splunk", "profiling", "always_on", "cpu_profiler"])
def test_invalid_profiling_block_fails_before_starting(profiling_contexts, key):
    config = {key: False}
    keys = ["splunk", "profiling", "always_on", "cpu_profiler"]
    for parent in reversed(keys[: keys.index(key)]):
        config = {parent: config}

    with pytest.raises(ConfigurationError, match=f"{key} must be a mapping"):
        configure_declarative_continuous_profiling(config, Resource({}))

    assert not profiling_contexts


@pytest.mark.parametrize(
    "exporter",
    [
        False,
        {"otlp_log_grpc": {}},
        {"otlp_log_http": False},
        {"otlp_log_http": {}, "console": {}},
        {"otlp_log_http": {"endpoint": 123}},
        {"otlp_log_http": {"headers": "invalid"}},
        {"otlp_log_http": {"timeout": "invalid"}},
    ],
)
def test_invalid_profile_exporter_fails_before_starting(profiling_contexts, exporter):
    with pytest.raises(ConfigurationError):
        configure_declarative_continuous_profiling(
            {"splunk": {"profiling": {"exporter": exporter, "always_on": {"cpu_profiler": {}}}}},
            Resource({}),
        )

    assert not profiling_contexts
