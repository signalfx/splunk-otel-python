#  Copyright Splunk Inc.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
import logging

from splunk_otel.env import Env


def test_env():
    e = Env()
    e.store = {
        "PREEXISTING": "preexisting",
        "FAVORITE_NUMBER": "42",
    }

    e.setdefault("PREEXISTING", "default")
    assert e.getval("PREEXISTING") == "preexisting"

    e.setdefault("FOO", "111")
    assert e.getval("FOO") == "111"

    e.setval("BAR", "222")
    assert e.getval("BAR") == "222"

    e.setval("TRUE_FLAG", "true")
    assert e.is_true("TRUE_FLAG")

    e.setval("FALSE_FLAG", "false")
    assert not e.is_true("FALSE_FLAG")

    e.list_append("MY_LIST", "a")
    assert e.getval("MY_LIST") == "a"
    e.list_append("MY_LIST", "b")
    assert e.getval("MY_LIST") == "a,b"

    assert e.getint("FAVORITE_NUMBER", 111) == 42
    assert e.getint("NOT_SET", 222) == 222


def test_get_invalid_int(caplog):
    with caplog.at_level(logging.WARNING):
        e = Env()
        e.store = {
            "FAVORITE_NUMBER": "bar",
        }
        assert e.getint("FAVORITE_NUMBER", 111) == 111
    assert "Invalid integer value" in caplog.text
