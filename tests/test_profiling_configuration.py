from unittest.mock import Mock

import pytest
from opentelemetry import trace
from opentelemetry._logs import NoOpLoggerProvider
from opentelemetry.propagate import get_global_textmap, set_global_textmap
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.configuration import ConfigurationError
from opentelemetry.sdk.resources import Resource

from splunk_otel.env import Env
from splunk_otel.profile import start_profiling
from splunk_otel.propagator import CallgraphsPropagator
from splunk_otel._declarative_profiling import _configure_declarative_profiling


@pytest.fixture
def logger_provider_configs():
    return []


@pytest.fixture
def profiling_contexts(monkeypatch, logger_provider_configs):
    contexts = []

    class FakeProfilingContext:
        def __init__(
            self, resource, interval_millis, logger, stacktrace_filter=None, instrumentation_source="continuous"
        ):
            self.resource = resource
            self.interval_millis = interval_millis
            self.logger = logger
            self.instrumentation_source = instrumentation_source
            self.started = False
            contexts.append(self)

        def start(self):
            self.started = True

        def stop(self):
            self.started = False

        def pause_after(self, _seconds):
            pass

    monkeypatch.setattr("splunk_otel.profile.ProfilingContext", FakeProfilingContext)
    monkeypatch.setattr("splunk_otel.callgraphs.span_processor.ProfilingContext", FakeProfilingContext)

    def _fake_create_logger_provider(logger_provider_config, _resource):
        logger_provider_configs.append(logger_provider_config)
        return NoOpLoggerProvider()

    monkeypatch.setattr("splunk_otel._declarative_profiling.create_logger_provider", _fake_create_logger_provider)
    return contexts


@pytest.mark.parametrize(
    ("cpu_profiler_config", "interval_millis"), [({}, 1000), (None, 1000), ({"sampling_interval": 250}, 250)]
)
def test_yaml_starts_continuous_profiling(monkeypatch, profiling_contexts, cpu_profiler_config, interval_millis):
    monkeypatch.setenv("SPLUNK_PROFILER_ENABLED", "false")
    monkeypatch.setenv("SPLUNK_PROFILER_CALL_STACK_INTERVAL", "9999")
    resource = Resource({"service.name": "yaml-service", "deployment.environment.name": "test"})

    _configure_declarative_profiling(
        {"splunk": {"profiling": {"always_on": {"cpu_profiler": cpu_profiler_config}}}}, resource
    )

    (context,) = profiling_contexts
    assert context.started
    assert context.interval_millis == interval_millis
    assert context.resource is resource


def test_start_profiling_uses_supplied_environment(monkeypatch, profiling_contexts):
    monkeypatch.setenv("OTEL_SERVICE_NAME", "process-service")
    monkeypatch.setenv("SPLUNK_PROFILER_CALL_STACK_INTERVAL", "9999")
    environment = Env({"OTEL_SERVICE_NAME": "environment-service", "SPLUNK_PROFILER_CALL_STACK_INTERVAL": "250"})

    context = start_profiling(environment)

    assert profiling_contexts == [context]
    assert context.started
    assert context.interval_millis == 250
    assert context.resource.attributes["service.name"] == "environment-service"


def test_start_profiling_without_arguments_uses_process_environment(monkeypatch, profiling_contexts):
    monkeypatch.setenv("OTEL_SERVICE_NAME", "process-service")
    monkeypatch.setenv("SPLUNK_PROFILER_CALL_STACK_INTERVAL", "500")
    monkeypatch.setenv("SPLUNK_PROFILER_ENABLED", "false")

    context = start_profiling()

    assert profiling_contexts == [context]
    assert context.started
    assert context.interval_millis == 500
    assert context.resource.attributes["service.name"] == "process-service"


@pytest.mark.parametrize("configuration_source", ["environment", "declarative"])
def test_continuous_profiling_stops_at_exit(monkeypatch, profiling_contexts, configuration_source):
    shutdown_callbacks = []

    def _fake_register_shutdown(callback):
        shutdown_callbacks.append(callback)

    monkeypatch.setattr("splunk_otel.profile._atexit.register", _fake_register_shutdown)
    if configuration_source == "environment":
        start_profiling(Env({"OTEL_SERVICE_NAME": "environment-service"}))
    else:
        _configure_declarative_profiling({"splunk": {"profiling": {"always_on": {"cpu_profiler": {}}}}}, Resource({}))

    (context,) = profiling_contexts
    assert context.started
    (shutdown,) = shutdown_callbacks
    shutdown()
    assert not context.started


@pytest.mark.parametrize(
    "distribution_config",
    [
        None,
        {},
        {"splunk": None},
        {"splunk": {"profiling": None}},
        {"splunk": {"profiling": {}}},
        {"splunk": {"profiling": {"always_on": None}}},
        {"splunk": {"profiling": {"always_on": {}}}},
        {"splunk": {"profiling": {"exporter": {"otlp_log_grpc": {}}}}},
    ],
)
def test_yaml_without_profiling_modes_does_not_start_profiling(
    monkeypatch, profiling_contexts, logger_provider_configs, distribution_config
):
    monkeypatch.setenv("SPLUNK_PROFILER_ENABLED", "true")
    monkeypatch.setenv("SPLUNK_SNAPSHOT_PROFILER_ENABLED", "true")

    _configure_declarative_profiling(distribution_config, Resource({}))

    assert not profiling_contexts
    assert not logger_provider_configs


@pytest.mark.parametrize("http_exporter_config", [None, {}, {"endpoint": None}, {"endpoint": ""}])
def test_unset_profile_endpoint_uses_sdk_default(
    monkeypatch, profiling_contexts, logger_provider_configs, http_exporter_config
):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:1/base")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", "http://localhost:1/logs")

    _configure_declarative_profiling(
        {
            "splunk": {
                "profiling": {
                    "always_on": {"cpu_profiler": {}},
                    "exporter": {"otlp_log_http": http_exporter_config},
                }
            }
        },
        Resource({}),
    )

    (logger_provider_config,) = logger_provider_configs
    assert logger_provider_config.processors[0].batch.exporter.otlp_http.endpoint == "http://localhost:4318/v1/logs"
    assert profiling_contexts[0].started


@pytest.mark.parametrize("interval_millis", [0, -1, True, 1.0, 1.5, "1000", None])
def test_invalid_sampling_interval_fails_before_starting(profiling_contexts, interval_millis):
    with pytest.raises(
        ConfigurationError,
        match=r"distribution\.splunk\.profiling\.always_on\.cpu_profiler\.sampling_interval",
    ):
        _configure_declarative_profiling(
            {"splunk": {"profiling": {"always_on": {"cpu_profiler": {"sampling_interval": interval_millis}}}}},
            Resource({}),
        )

    assert not profiling_contexts


@pytest.mark.parametrize("key", ["splunk", "profiling", "always_on", "cpu_profiler"])
def test_invalid_profiling_block_fails_before_starting(profiling_contexts, key):
    distribution_config = {key: False}
    keys = ["splunk", "profiling", "always_on", "cpu_profiler"]
    for parent in reversed(keys[: keys.index(key)]):
        distribution_config = {parent: distribution_config}

    with pytest.raises(ConfigurationError, match=key):
        _configure_declarative_profiling(distribution_config, Resource({}))

    assert not profiling_contexts


@pytest.mark.parametrize(
    "exporter_config",
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
@pytest.mark.parametrize("profiling_mode", [{"always_on": {"cpu_profiler": {}}}, {"callgraphs": {}}])
def test_invalid_profile_exporter_fails_before_starting(profiling_contexts, exporter_config, profiling_mode):
    with pytest.raises(ConfigurationError):
        _configure_declarative_profiling(
            {"splunk": {"profiling": {"exporter": exporter_config, **profiling_mode}}},
            Resource({}),
        )

    assert not profiling_contexts


@pytest.fixture
def tracer_provider(monkeypatch):
    provider = TracerProvider(shutdown_on_exit=False)
    monkeypatch.setattr(trace, "get_tracer_provider", lambda: provider)
    original_propagator = get_global_textmap()
    yield provider
    provider.shutdown()
    set_global_textmap(original_propagator)


@pytest.mark.parametrize(
    ("callgraphs_config", "interval_millis", "probability"),
    [(None, 10, 0.01), ({}, 10, 0.01), ({"sampling_interval": 25, "selection_probability": 0.5}, 25, 0.5)],
)
@pytest.mark.usefixtures("tracer_provider")
def test_yaml_configures_callgraphs(monkeypatch, profiling_contexts, callgraphs_config, interval_millis, probability):
    monkeypatch.setenv("SPLUNK_SNAPSHOT_PROFILER_ENABLED", "false")
    monkeypatch.setenv("SPLUNK_SNAPSHOT_SAMPLING_INTERVAL", "9999")
    monkeypatch.setenv("SPLUNK_SNAPSHOT_SELECTION_PROBABILITY", "0.9")
    resource = Resource({"service.name": "yaml-service"})

    _configure_declarative_profiling({"splunk": {"profiling": {"callgraphs": callgraphs_config}}}, resource)

    (context,) = profiling_contexts
    assert context.resource is resource
    assert context.interval_millis == interval_millis
    assert context.instrumentation_source == "snapshot"
    assert not context.started
    propagators = get_global_textmap()._propagators  # noqa SLF001
    assert isinstance(propagators[-1], CallgraphsPropagator)
    assert propagators[-1].selection_probability == probability


@pytest.mark.usefixtures("tracer_provider")
@pytest.mark.parametrize("cpu_profiler_config", [None, {}])
@pytest.mark.parametrize("callgraphs_config", [None, {}])
def test_both_profiling_modes_share_one_dedicated_logger(
    profiling_contexts, logger_provider_configs, cpu_profiler_config, callgraphs_config
):
    _configure_declarative_profiling(
        {
            "splunk": {
                "profiling": {"always_on": {"cpu_profiler": cpu_profiler_config}, "callgraphs": callgraphs_config}
            }
        },
        Resource({}),
    )

    continuous, callgraphs = profiling_contexts
    assert continuous.instrumentation_source == "continuous"
    assert callgraphs.instrumentation_source == "snapshot"
    assert continuous.started
    assert continuous.logger is callgraphs.logger
    assert len(logger_provider_configs) == 1


@pytest.mark.parametrize("enable_continuous", [False, True])
def test_incompatible_tracer_provider_fails_before_profiling_setup(
    monkeypatch, profiling_contexts, logger_provider_configs, enable_continuous
):
    provider = trace.NoOpTracerProvider()
    monkeypatch.setattr(trace, "get_tracer_provider", lambda: provider)
    profiling_config = {"callgraphs": {}}
    if enable_continuous:
        profiling_config["always_on"] = {"cpu_profiler": {}}

    with pytest.raises(ConfigurationError, match="incompatible global tracer provider"):
        _configure_declarative_profiling({"splunk": {"profiling": profiling_config}}, Resource({}))

    assert not profiling_contexts
    assert not logger_provider_configs
    assert trace.get_tracer_provider() is provider


def test_callgraphs_cleans_up_when_another_provider_registers_first(
    monkeypatch, profiling_contexts, logger_provider_configs
):
    candidate = TracerProvider(shutdown_on_exit=False)
    competing_provider = trace.NoOpTracerProvider()
    shutdown = Mock(wraps=candidate.shutdown)
    monkeypatch.setattr(candidate, "shutdown", shutdown)
    monkeypatch.setattr(trace, "get_tracer_provider", trace.ProxyTracerProvider)

    def _fake_create_tracer_provider(**_kwargs):
        return candidate

    monkeypatch.setattr("splunk_otel._declarative_profiling.create_tracer_provider", _fake_create_tracer_provider)

    def _fake_register_tracer_provider(_provider):
        monkeypatch.setattr(trace, "get_tracer_provider", lambda: competing_provider)

    monkeypatch.setattr(trace, "set_tracer_provider", _fake_register_tracer_provider)

    with pytest.raises(ConfigurationError, match="could not install a tracer provider"):
        _configure_declarative_profiling(
            {"splunk": {"profiling": {"always_on": {"cpu_profiler": {}}, "callgraphs": {}}}}, Resource({})
        )

    assert trace.get_tracer_provider() is competing_provider
    shutdown.assert_called_once_with()
    assert not profiling_contexts
    assert not logger_provider_configs


@pytest.mark.parametrize("callgraphs_config", [False, [], "enabled"])
def test_invalid_callgraphs_block_fails_before_starting(profiling_contexts, callgraphs_config):
    with pytest.raises(ConfigurationError, match=r"distribution\.splunk\.profiling\.callgraphs"):
        _configure_declarative_profiling({"splunk": {"profiling": {"callgraphs": callgraphs_config}}}, Resource({}))

    assert not profiling_contexts


@pytest.mark.parametrize(
    ("key", "value"),
    [("sampling_interval", value) for value in [0, -1, True, 1.0, "10", None]]
    + [
        ("selection_probability", value) for value in [0, 0.0, -0.1, 1.1, True, "0.5", None, float("nan"), float("inf")]
    ],
)
def test_invalid_callgraphs_setting_fails_before_either_mode_starts(profiling_contexts, key, value):
    with pytest.raises(ConfigurationError, match=rf"distribution\.splunk\.profiling\.callgraphs\.{key}"):
        _configure_declarative_profiling(
            {"splunk": {"profiling": {"always_on": {"cpu_profiler": {}}, "callgraphs": {key: value}}}}, Resource({})
        )

    assert not profiling_contexts
