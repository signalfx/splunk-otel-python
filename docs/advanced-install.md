# Advanced Installation

## Bootstrap: List requirements instead of installing them

The `splk-py-trace-bootstrap` command can optionally print out the list of
packages it would install if you chose. In order to do so, pass
`-a=requirements` CLI argument to it. For example,

```
splk-py-trace-bootstrap -a requirements
```

Will output something like the following:

```
opentelemetry-instrumentation-falcon>=0.15b0
opentelemetry-instrumentation-jinja2>=0.15b0
opentelemetry-instrumentation-requests>=0.15b0
opentelemetry-instrumentation-sqlite3>=0.15b0
```

You can pipe the output of this command to append the new packages to your
requirements.txt file or to something like `poetry add`.

## Installing only a subset of dependencies

Installing `splunk-opentelemetry[all]` automatically pulls in all of the
optional dependencies. These include the OTLP gRPC exporter, the Jaeger Thrift
exporter and the B3 propagator. If you'd like to install only the packages you
need, you can use any combination of `oltp`, `jaeger` and `b3`. For example, in
order to install only `otlp` exporter, you can run

```
pip install splunk-opentelemetry[otlp]
```

To install the Jaeger Thrift exporter and the B3 propagator, you can run

```
pip install splunk-opentelemetry[jaeger,b3]
```
