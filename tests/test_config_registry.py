# Copyright Splunk Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from splunk_otel.opamp.config_registry import ConfigRegistry


def _raise(exc):
    raise exc


class TestOpampConfigRegistry:
    def test_get_all_returns_registered_values(self):
        registry = ConfigRegistry()
        registry.register("KEY_A", getter=lambda: "val_a")
        registry.register("KEY_B", getter=lambda: "val_b")
        assert registry.get_all() == {"KEY_A": "val_a", "KEY_B": "val_b"}

    def test_get_all_empty(self):
        assert ConfigRegistry().get_all() == {}

    def test_get_all_skips_failing_getter(self):
        registry = ConfigRegistry()
        registry.register("GOOD", getter=lambda: "ok")
        registry.register("BAD", getter=lambda: 1 / 0)
        result = registry.get_all()
        assert result == {"GOOD": "ok"}
        assert "BAD" not in result

    def test_apply_calls_set_callback(self):
        received = {}
        registry = ConfigRegistry()
        registry.register("KEY", getter=lambda: "old", setter=lambda _v: received.update({"KEY": _v}))
        updated_keys = registry.update({"KEY": "new"})
        assert updated_keys == ["KEY"]
        assert received == {"KEY": "new"}

    def test_apply_skips_unknown_key(self):
        registry = ConfigRegistry()
        updated_keys = registry.update({"UNKNOWN": "x"})
        assert updated_keys == []

    def test_apply_skips_read_only_key(self):
        registry = ConfigRegistry()
        registry.register("RO", getter=lambda: "v")  # no setter
        updated_keys = registry.update({"RO": "new"})
        assert updated_keys == []

    def test_apply_skips_failing_setter(self):
        registry = ConfigRegistry()
        registry.register("KEY", getter=lambda: "v", setter=lambda _v: _raise(RuntimeError("boom")))
        updated_keys = registry.update({"KEY": "new"})
        assert updated_keys == []

    def test_apply_partial_success(self):
        received = {}
        registry = ConfigRegistry()
        registry.register("GOOD", getter=lambda: "v", setter=lambda _v: received.update({"GOOD": _v}))
        registry.register("BAD", getter=lambda: "v", setter=lambda _v: _raise(RuntimeError()))
        updated_keys = registry.update({"GOOD": "g", "BAD": "b"})
        assert updated_keys == ["GOOD"]
        assert received == {"GOOD": "g"}
