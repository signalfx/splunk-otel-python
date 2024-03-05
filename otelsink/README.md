# OTel Sink

This library makes it easy to run an OTel GRPC endpoint for metrics, traces, and logs.

## Installation

```
cd otelsink
pip install .
```

## Operation

You can run OTel Sink either from the command line by using the `otelsink` command (installed by pip),
or programatically.

Either way, a gRPC server is started on 0.0.0.0:4317.

### Command Line Invocation

```
% otelsink
starting otelsink with print handler
```

### Programatic Invocation

```
    class MyHandler(RequestHandler):
        def handle_logs(self, request, context):
            print(f"received log request: {request}")

        def handle_metrics(self, request, context):
            print(f"received metrics request: {request}")

        def handle_trace(self, request, context):
            print(f"received trace request: {request}")


    sink = GrpcSink(MyHandler())
    sink.start()
    sink.wait_for_termination()

```

## Development

Note that this project directory is set up to use Hatch to manage the build. Eventually we would like to migrate all
builds in this repo to Hatch, matching the upstream opentelemetry-python projects.
