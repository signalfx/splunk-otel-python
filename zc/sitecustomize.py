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

import syslog

DEFAULT_SERVICE_NAME = 'default_service_name'

def get_service_name_candidates():
    import os
    import sys
    import socket
    yield os.path.basename(sys.argv[0])
    yield os.path.basename(os.getcwd())
    yield socket.gethostname()


def get_service_name():
    return next((name for name in get_service_name_candidates() if name), DEFAULT_SERVICE_NAME)


def set_up():
    syslog.openlog("splunk-otel-python-zero-config", logoption=syslog.LOG_PID, facility=syslog.LOG_USER)
    syslog.syslog(syslog.LOG_INFO, 'Setting up OpenTelemetry through sitecustomize.py')

    import os
    from opentelemetry.instrumentation.auto_instrumentation._load import (
        _load_configurators,
        _load_distro,
        _load_instrumentors,
    )
    from opentelemetry.sdk.environment_variables import OTEL_SERVICE_NAME
    if OTEL_SERVICE_NAME not in os.environ:
        service_name = get_service_name()
        syslog.syslog(syslog.LOG_INFO, f'Setting OTEL_SERVICE_NAME [{service_name}]')
        os.environ[OTEL_SERVICE_NAME] = service_name
    distro = _load_distro()
    distro.configure()
    _load_configurators()
    _load_instrumentors(distro)


def main():
    try:
        set_up()
    except Exception as e:
        syslog.syslog(syslog.LOG_ERR, f'Setting up OpenTelemetry via sitecustomize.py failed, skipping {e}')
    else:
        syslog.syslog(syslog.LOG_INFO, 'OpenTelemetry successfully set up')


main()
