import base64
import gzip
import json
import random
import time
from collections import OrderedDict
from os.path import abspath, dirname

import pytest
from google.protobuf.json_format import MessageToDict
from opentelemetry._logs import Logger
from opentelemetry.sdk.resources import Resource
from splunk_otel import profile_pb2
from splunk_otel.profile import (
    _get_line,
    _pb_profile_to_str,
    _ProfileScraper,
    _stacktraces_to_cpu_profile,
    _StringTable,
)


@pytest.fixture
def stacktraces_fixture():
    return load_json("stacktraces.in.json")


@pytest.fixture
def thread_states_fixture():
    out = {}
    og = load_json("thread_states.in.json")
    for k, v in og.items():
        out[int(k)] = v
    return out


@pytest.fixture
def pb_profile_fixture():
    return load_json("pb_profile.out.json")


def load_json(fname):
    parent_dir = dirname(abspath(__file__))
    with open(f"{parent_dir}/fixtures/{fname}") as f:
        return json.load(f)


def test_basic_proto_serialization():
    # noinspection PyUnresolvedReferences
    profile = profile_pb2.Profile()
    serialized = _pb_profile_to_str(profile)
    decoded_profile = _pb_profile_from_str(serialized)
    assert profile == decoded_profile


def test_stacktraces_to_cpu_profile(stacktraces_fixture, pb_profile_fixture, thread_states_fixture):
    time_seconds = 1726760000  # corresponds to the timestamp in the fixture
    interval_millis = 100
    profile = _stacktraces_to_cpu_profile(stacktraces_fixture, thread_states_fixture, interval_millis, time_seconds)
    assert pb_profile_fixture == MessageToDict(profile)


def test_get_line():
    line = _get_line(OrderedDict(), _StringTable(), "test", "test", 42)
    assert line.line == 42


def test_get_line_none():
    line = _get_line(OrderedDict(), _StringTable(), "test", "test", None)
    assert line.line == -1


def test_profile_scraper(stacktraces_fixture):
    time_seconds = 1726760000
    logger = _FakeLogger()
    ps = _ProfileScraper(
        Resource({}),
        {},
        100,
        logger,
        collect_stacktraces_func=lambda: stacktraces_fixture,
        time_func=lambda: time_seconds,
    )
    ps.tick()

    log_record = logger.log_records[0]

    assert log_record.timestamp == int(time_seconds * 1e9)
    assert len(MessageToDict(_pb_profile_from_str(log_record.body))) == 4  # sanity check
    assert log_record.attributes["profiling.data.total.frame.count"] == 30


def _pb_profile_from_str(stringified: str) -> profile_pb2.Profile:
    byte_array = base64.b64decode(stringified)
    decompressed = gzip.decompress(byte_array)
    out = profile_pb2.Profile()
    out.ParseFromString(decompressed)
    return out


def _do_work(time_ms):
    now = time.time()
    target = now + time_ms / 1000.0

    total = 0.0
    while now < target:
        value = random.random()
        for _ in range(10000):
            value = value + random.random()

        total = total + value

        now = time.time()
        time.sleep(0.01)

    return total


class _FakeLogger(Logger):
    def __init__(self):
        super().__init__("fake-logger")
        self.log_records = []

    def emit(self, record) -> None:
        self.log_records.append(record)
