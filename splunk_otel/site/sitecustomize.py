import os
import sys
from logging import getLogger

from splunk_otel.tracing import start_tracing

logger = getLogger(__file__)


def init():
    start_tracing()


if (
    hasattr(sys, "argv")
    and sys.argv[0].split(os.path.sep)[-1] == "celery"
    and "worker" in sys.argv
):
    from celery.signals import worker_process_init

    @worker_process_init.connect(weak=False)
    def init_celery(*args, **kwargs):
        init()


else:
    init()
