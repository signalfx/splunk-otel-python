from lib import project_path

if __name__ == "__main__":
    import sqlite3

    from opentelemetry.instrumentation.dbapi import trace_integration

    trace_integration(sqlite3, "connect", "sqlite")

    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE t (x INTEGER)")
    cursor.execute("INSERT INTO t VALUES (1)")
    cursor.execute("INSERT INTO t VALUES (2)")
    cursor.execute("SELECT * FROM t")

    rows = list(cursor)
    assert rows == [(1,), (2,)], f"Expected [(1,), (2,)], got {rows}"


class DbapiCursorIterOtelTest:
    def requirements(self):
        return (project_path(), "opentelemetry-instrumentation-dbapi")

    def environment_variables(self):
        return {
            "OTEL_SERVICE_NAME": "dbapi-cursor-iter-test",
            "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS": "system_metrics",
        }

    def wrapper_command(self):
        return ""

    def on_start(self):
        return None

    def on_stop(self, telemetry, stdout: str, stderr: str, returncode: int) -> None:
        assert returncode == 0, f"Script failed with returncode {returncode}.\nstdout: {stdout}\nstderr: {stderr}"
