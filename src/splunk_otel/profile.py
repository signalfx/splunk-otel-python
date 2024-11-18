import base64
import gzip
import logging
import sys
import threading
import time
import traceback
from collections import OrderedDict
from traceback import StackSummary

import opentelemetry.context
import wrapt
from opentelemetry._logs import Logger, SeverityNumber, get_logger
from opentelemetry.context import Context
from opentelemetry.instrumentation.version import __version__ as version
from opentelemetry.sdk._logs import LogRecord
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import TraceFlags
from opentelemetry.trace.propagation import _SPAN_KEY

from splunk_otel import profile_pb2
from splunk_otel.env import Env

_SERVICE_NAME_ATTR = "service.name"
_SPLUNK_DISTRO_VERSION_ATTR = "splunk.distro.version"
_NO_SERVICE_NAME_WARNING = """The service.name attribute is not set, which may make your service difficult to identify.
Set your service name using the OTEL_SERVICE_NAME environment variable.
e.g. `OTEL_SERVICE_NAME="<YOUR_SERVICE_NAME_HERE>"`"""
_DEFAULT_SERVICE_NAME = "unnamed-python-service"

_profile_timer = None
_pylogger = logging.getLogger(__name__)


def start_profiling():
    tcm = _ThreadContextMapping()
    tcm.wrap_context_methods()

    period_millis = 100
    resource = _mk_resource(Env().getval("OTEL_SERVICE_NAME"))
    logger = get_logger("splunk-profiler")
    scraper = _ProfileScraper(resource, tcm.get_thread_states(), period_millis, logger)

    global _profile_timer  # noqa PLW0603
    _profile_timer = _PeriodicTimer(period_millis, scraper.tick)
    _profile_timer.start()


def stop_profiling():
    _profile_timer.stop()


def _mk_resource(service_name) -> Resource:
    if service_name:
        resolved_name = service_name
    else:
        _pylogger.warning(_NO_SERVICE_NAME_WARNING)
        resolved_name = _DEFAULT_SERVICE_NAME
    return Resource.create(
        {
            _SPLUNK_DISTRO_VERSION_ATTR: version,
            _SERVICE_NAME_ATTR: resolved_name,
        }
    )


class _ThreadContextMapping:
    def __init__(self):
        self.thread_states = {}

    def get_thread_states(self):
        return self.thread_states

    def wrap_context_methods(self):
        wrapt.wrap_function_wrapper(opentelemetry.context, "attach", self.wrap_context_attach())
        wrapt.wrap_function_wrapper(opentelemetry.context, "detach", self.wrap_context_detach())

    def wrap_context_attach(self):
        def wrapper(wrapped, _instance, args, kwargs):
            token = wrapped(*args, **kwargs)

            maybe_context = args[0] if args else None

            if maybe_context:
                span = maybe_context.get(_SPAN_KEY)

                if span:
                    thread_id = threading.get_ident()
                    context = span.get_span_context()
                    self.thread_states[thread_id] = (
                        context.trace_id,
                        context.span_id,
                    )

            return token

        return wrapper

    def wrap_context_detach(self):
        def wrapper(wrapped, _instance, args, kwargs):
            token = args[0] if args else None

            if token:
                prev = token.old_value
                thread_id = threading.get_ident()
                if isinstance(prev, Context):
                    span = prev.get(_SPAN_KEY)

                    if span:
                        context = span.get_span_context()
                        self.thread_states[thread_id] = (
                            context.trace_id,
                            context.span_id,
                        )
                    else:
                        self.thread_states[thread_id] = None
                else:
                    self.thread_states[thread_id] = None
            return wrapped(*args, **kwargs)

        return wrapper


def _collect_stacktraces():
    out = []
    frames = sys._current_frames()  # noqa SLF001

    for thread_id, frame in frames.items():
        stack_summary = _extract_stack_summary(frame)
        frames = [(sf.filename, sf.name, sf.lineno) for sf in stack_summary]
        out.append(
            {
                "frames": frames,
                "tid": thread_id,
            }
        )
    return out


class _ProfileScraper:
    def __init__(
        self,
        resource,
        thread_states,
        period_millis,
        logger: Logger,
        collect_stacktraces_func=_collect_stacktraces,
        time_func=time.time,
    ):
        self.resource = resource
        self.thread_states = thread_states
        self.period_millis = period_millis
        self.collect_stacktraces = collect_stacktraces_func
        self.time = time_func
        self.logger = logger

    def tick(self):
        stacktraces = self.collect_stacktraces()
        log_record = self.mk_log_record(stacktraces)
        self.logger.emit(log_record)

    def mk_log_record(self, stacktraces):
        lengths = (len(trace["frames"]) for trace in stacktraces)
        total_frame_count = sum(lengths)

        time_seconds = self.time()

        pb_profile = _stacktraces_to_cpu_profile(stacktraces, self.thread_states, self.period_millis, time_seconds)
        pb_profile_str = _pb_profile_to_str(pb_profile)

        return LogRecord(
            timestamp=int(time_seconds * 1e9),
            trace_id=0,
            span_id=0,
            trace_flags=TraceFlags(0x01),
            severity_number=SeverityNumber.UNSPECIFIED,
            body=pb_profile_str,
            resource=self.resource,
            attributes={
                "profiling.data.format": "pprof-gzip-base64",
                "profiling.data.type": "cpu",
                "com.splunk.sourcetype": "otel.profiling",
                "profiling.data.total.frame.count": total_frame_count,
            },
        )


def _pb_profile_to_str(pb_profile) -> str:
    serialized = pb_profile.SerializeToString()
    compressed = gzip.compress(serialized)
    b64encoded = base64.b64encode(compressed)
    return b64encoded.decode()


class _PeriodicTimer:
    def __init__(self, period_millis, target):
        self.period_seconds = period_millis / 1e3
        self.target = target
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.sleep = time.sleep

    def start(self):
        self.thread.start()

    def _loop(self):
        while True:
            start_time_seconds = time.time()
            self.target()
            elapsed_seconds = time.time() - start_time_seconds
            sleep_seconds = max(0, self.period_seconds - elapsed_seconds)
            time.sleep(sleep_seconds)

    def stop(self):
        self.thread.join()


class _StringTable:
    def __init__(self):
        self.strings = OrderedDict()

    def index(self, token):
        idx = self.strings.get(token)

        if idx:
            return idx

        idx = len(self.strings)
        self.strings[token] = idx
        return idx

    def keys(self):
        return list(self.strings.keys())


def _get_location(functions_table, str_table, locations_table, frame):
    (file_name, function_name, line_no) = frame
    key = f"{file_name}:{function_name}:{line_no}"
    location = locations_table.get(key)

    if location is None:
        location = profile_pb2.Location()
        location.id = len(locations_table) + 1
        line = _get_line(functions_table, str_table, file_name, function_name, line_no)
        location.line.append(line)
        locations_table[key] = location

    return location


def _get_line(functions_table, str_table, file_name, function_name, line_no):
    line = profile_pb2.Line()
    line.function_id = _get_function(functions_table, str_table, file_name, function_name).id
    line.line = line_no if line_no != 0 else -1
    return line


def _get_function(functions_table, str_table, file_name, function_name):
    key = f"{file_name}:{function_name}"
    func = functions_table.get(key)

    if func is None:
        name_id = str_table.index(function_name)
        func = profile_pb2.Function()
        func.id = len(functions_table) + 1
        func.name = name_id
        func.system_name = name_id
        func.filename = str_table.index(file_name)
        functions_table[key] = func

    return func


def _extract_stack_summary(frame):
    stack_iterator = traceback.walk_stack(frame)
    out = StackSummary.extract(stack_iterator, limit=None, lookup_lines=False)
    out.reverse()
    return out


def _stacktraces_to_cpu_profile(stacktraces, thread_states, period_millis, time_seconds):
    str_table = _StringTable()
    locations_table = OrderedDict()
    functions_table = OrderedDict()

    timestamp_unix_millis = int(time_seconds * 1e3)

    timestamp_key = str_table.index("source.event.time")
    trace_id_key = str_table.index("trace_id")
    span_id_key = str_table.index("span_id")
    thread_id_key = str_table.index("thread.id")
    event_period_key = str_table.index("source.event.period")

    pb_profile = profile_pb2.Profile()

    event_period_label = profile_pb2.Label()
    event_period_label.key = event_period_key
    event_period_label.num = period_millis

    samples = []
    for stacktrace in stacktraces:
        thread_id = stacktrace["tid"]

        timestamp_label = profile_pb2.Label()
        timestamp_label.key = timestamp_key
        timestamp_label.num = timestamp_unix_millis

        thread_id_label = profile_pb2.Label()
        thread_id_label.key = thread_id_key
        thread_id_label.num = thread_id

        labels = [timestamp_label, event_period_label, thread_id_label]

        trace_context = thread_states.get(thread_id)
        if trace_context:
            (trace_id, span_id) = trace_context

            trace_id_label = profile_pb2.Label()
            trace_id_label.key = trace_id_key
            trace_id_label.str = str_table.index(f"{trace_id:016x}")
            labels.append(trace_id_label)

            span_id_label = profile_pb2.Label()
            span_id_label.key = span_id_key
            span_id_label.str = str_table.index(f"{span_id:08x}")
            labels.append(span_id_label)

        sample = profile_pb2.Sample()

        location_ids = []

        for frame in reversed(stacktrace["frames"]):
            location = _get_location(functions_table, str_table, locations_table, frame)
            location_ids.append(location.id)

        sample.location_id.extend(location_ids)
        sample.label.extend(labels)

        samples.append(sample)

    pb_profile.sample.extend(samples)
    pb_profile.string_table.extend(str_table.keys())
    pb_profile.function.extend(list(functions_table.values()))
    pb_profile.location.extend(list(locations_table.values()))

    return pb_profile
