import base64
import gzip
import sys
import threading
import time
import traceback
from collections import OrderedDict
from traceback import StackSummary
from typing import Callable, Optional, Literal

import opentelemetry.context
import wrapt
from opentelemetry._logs import Logger, LogRecord, SeverityNumber, get_logger
from opentelemetry.context import Context
from opentelemetry.instrumentation.version import __version__ as version
from opentelemetry.sdk._logs import ReadWriteLogRecord
from opentelemetry.sdk.environment_variables import OTEL_SERVICE_NAME
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import (
    NonRecordingSpan,
    SpanContext,
    TraceFlags,
    set_span_in_context,
)
from opentelemetry.trace.propagation import _SPAN_KEY

from splunk_otel import profile_pb2
from splunk_otel.env import (
    SPLUNK_PROFILER_CALL_STACK_INTERVAL,
    SPLUNK_PROFILER_ENABLED,
    Env,
)

_DEFAULT_PROF_CALL_STACK_INTERVAL_MILLIS = 1000
_SERVICE_NAME_ATTR = "service.name"
_SPLUNK_DISTRO_VERSION_ATTR = "splunk.distro.version"
_SCOPE_VERSION = "0.2.0"
_SCOPE_NAME = "otel.profiling"

_thread_states = {}
_context_tracking_started = False


class ProfilingContext:
    _timer = None

    def __init__(
        self,
        service_name: str,
        interval_millis: int,
        stacktrace_filter: Optional[Callable[[list[dict], dict], list[dict]]] = None,
        instrumentation_source: Optional[Literal["continuous", "snapshot"]] = "continuous",
    ):
        start_thread_context_tracking()
        resource = _mk_resource(service_name)
        logger = get_logger(_SCOPE_NAME, _SCOPE_VERSION)
        scraper = _ProfileScraper(
            resource,
            _thread_states,
            interval_millis,
            logger,
            stacktrace_filter=stacktrace_filter,
            instrumentation_source=instrumentation_source,
        )
        self._timer = _IntervalTimer(interval_millis, scraper.tick)

    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def pause_after(self, seconds: float):
        self._timer.pause_after(seconds)


def _start_profiling_if_enabled(env=None):
    env = env or Env()
    if env.is_true(SPLUNK_PROFILER_ENABLED):
        start_profiling(env)


def start_profiling(env=None):
    env = env or Env()
    interval_millis = env.getint(SPLUNK_PROFILER_CALL_STACK_INTERVAL, _DEFAULT_PROF_CALL_STACK_INTERVAL_MILLIS)
    svcname = env.getval(OTEL_SERVICE_NAME)

    ctx = ProfilingContext(svcname, interval_millis)
    ctx.start()
    return ctx


def _mk_resource(service_name) -> Resource:
    return Resource.create(
        {
            _SPLUNK_DISTRO_VERSION_ATTR: version,
            _SERVICE_NAME_ATTR: service_name,
        }
    )


def start_thread_context_tracking():
    global _context_tracking_started  # noqa PLW0603
    if _context_tracking_started:
        return
    _context_tracking_started = True

    wrapt.wrap_function_wrapper(opentelemetry.context, "attach", _wrap_context_attach)
    wrapt.wrap_function_wrapper(opentelemetry.context, "detach", _wrap_context_detach)


def _wrap_context_attach(wrapped, _instance, args, kwargs):
    token = wrapped(*args, **kwargs)

    maybe_context = args[0] if args else None

    if maybe_context:
        span = maybe_context.get(_SPAN_KEY)

        if span:
            thread_id = threading.get_ident()
            context = span.get_span_context()
            _thread_states[thread_id] = (
                context.trace_id,
                context.span_id,
            )

    return token


def _wrap_context_detach(wrapped, _instance, args, kwargs):
    token = args[0] if args else None

    if token:
        prev = token.old_value
        thread_id = threading.get_ident()
        if isinstance(prev, Context):
            span = prev.get(_SPAN_KEY)

            if span:
                context = span.get_span_context()
                _thread_states[thread_id] = (
                    context.trace_id,
                    context.span_id,
                )
            else:
                _thread_states[thread_id] = None
        else:
            _thread_states[thread_id] = None
    return wrapped(*args, **kwargs)


def _collect_stacktraces():
    out = []
    frames = sys._current_frames()  # noqa SLF001
    profile_scraper_thread_id = threading.get_ident()
    for thread_id, frame in frames.items():
        if thread_id == profile_scraper_thread_id:
            continue
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
        interval_millis,
        logger: Logger,
        collect_stacktraces_func=_collect_stacktraces,
        time_func=time.time,
        stacktrace_filter: Optional[Callable[[list[dict], dict], list[dict]]] = None,
        instrumentation_source: Optional[Literal["continuous", "snapshot"]] = "continuous",
    ):
        self.resource = resource
        self.thread_states = thread_states
        self.interval_millis = interval_millis
        self.collect_stacktraces = collect_stacktraces_func
        self.time = time_func
        self.logger = logger
        self.stacktrace_filter = stacktrace_filter
        self.instrumentation_source = instrumentation_source

    def tick(self):
        stacktraces = self.collect_stacktraces()

        if self.stacktrace_filter is not None:
            stacktraces = self.stacktrace_filter(stacktraces, self.thread_states)

        if len(stacktraces) == 0:
            return

        log_record = self.mk_log_record(stacktraces)
        self.logger.emit(log_record)

    def mk_log_record(self, stacktraces):
        lengths = (len(trace["frames"]) for trace in stacktraces)
        total_frame_count = sum(lengths)

        time_seconds = self.time()

        pb_profile = _stacktraces_to_cpu_profile(stacktraces, self.thread_states, self.interval_millis, time_seconds)
        pb_profile_str = _pb_profile_to_str(pb_profile)

        span_context = SpanContext(
            trace_id=0,
            span_id=0,
            is_remote=False,
            trace_flags=TraceFlags(0x01),
        )
        # Build an explicit Context so LogRecord doesn't fall back to the current span
        # (trace_id/span_id=0 are falsy) and keeps the wire format unchanged.
        log_context = set_span_in_context(
            NonRecordingSpan(span_context),
            Context(),
        )
        log_record = LogRecord(
            timestamp=int(time_seconds * 1e9),
            context=log_context,
            severity_number=SeverityNumber.UNSPECIFIED,
            body=pb_profile_str,
            attributes={
                "profiling.data.format": "pprof-gzip-base64",
                "profiling.data.type": "cpu",
                "com.splunk.sourcetype": "otel.profiling",
                "profiling.data.total.frame.count": total_frame_count,
                "profiling.instrumentation.source": self.instrumentation_source,
            },
        )
        instrumentation_scope = getattr(
            self.logger,
            "_instrumentation_scope",
            None,
        )
        return ReadWriteLogRecord(
            log_record=log_record,
            resource=self.resource,
            instrumentation_scope=instrumentation_scope,
        )


def _pb_profile_to_str(pb_profile) -> str:
    serialized = pb_profile.SerializeToString()
    compressed = gzip.compress(serialized)
    b64encoded = base64.b64encode(compressed)
    return b64encoded.decode()


class _IntervalTimer:
    def __init__(self, interval_millis, target):
        self.interval_seconds = interval_millis / 1e3
        self.target = target
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.running = False
        self.pause_at = None
        self.wakeup_event = threading.Event()

    def start(self):
        self.pause_at = None
        self.wakeup_event.set()

        if self.running:
            return

        self.running = True
        self.thread.start()

    def _loop(self):
        while self.running:
            start_time_seconds = time.monotonic()

            if self.pause_at is not None and start_time_seconds >= self.pause_at:
                # The pause deadline has been reached, sleep until woken again.
                self.wakeup_event.wait()
                self.pause_at = None
                continue

            self.target()
            elapsed_seconds = time.monotonic() - start_time_seconds
            sleep_seconds = max(0, self.interval_seconds - elapsed_seconds)
            time.sleep(sleep_seconds)

    def stop(self):
        self.running = False
        self.pause_at = None
        self.wakeup_event.set()
        self.thread.join()

    def pause_after(self, seconds: float):
        # The timer will stay running until pause_at has been reached.
        self.pause_at = time.monotonic() + seconds
        self.wakeup_event.clear()


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
    if line_no is None or line_no == 0:
        line.line = -1
    else:
        line.line = line_no
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


def _stacktraces_to_cpu_profile(stacktraces, thread_states, interval_millis, time_seconds):
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
    event_period_label.num = interval_millis

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
