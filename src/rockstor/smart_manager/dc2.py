from gevent import monkey
monkey.patch_all()

import gevent
from socketio.server import SocketIOServer
from socketio import socketio_manage
from socketio.namespace import BaseNamespace
from socketio.mixins import BroadcastMixin

from django.conf import settings
from system.osi import (uptime, kernel_info)

from system.services import service_status
import logging
logger = logging.getLogger(__name__)


class ServicesNamespace(BaseNamespace, BroadcastMixin):
    def recv_connect(self):
        self.emit('services:connected', {
            'key': 'services:connected', 'data': 'connected'
        })
        self.spawn(self.send_service_statuses)

    def recv_disconnect(self):
        self.disconnect(silent=True)

    def send_service_statuses(self):
        # TODO: key/value pairs of the shortened, longer name for each service
        # check to see what the collection looks like (if there is a shortened name)
        # Iterate through the collection and assign the values accordingly
        services = {'nfs', 'smb', 'ntpd', 'winbind', 'netatalk',
                    'snmpd', 'docker', 'smartd', 'replication'
                    'nis', 'ldap', 'sftp', 'data-collector', 'smartd',
                    'service-monitor', 'docker', 'task-scheduler'}
        data = {}
        for service in services:
            data[service] = {}
            output, error, return_code = service_status(service)
            if (return_code == 0):
                data[service]['running'] = return_code
            else:
                data[service]['running'] = return_code

        self.emit('services:get_services', {
            'data': data, 'key': 'services:get_services'
        })

        gevent.sleep(30)


# TODO: Create a base class that runs all other classes within a context manager
class SysinfoNamespace(BaseNamespace, BroadcastMixin):
    start = False
    supported_kernel = settings.SUPPORTED_KERNEL_VERSION

    # This function is run once on every connection
    def recv_connect(self):
        self.emit("sysinfo:sysinfo", {
            "key": "sysinfo:connected", "data": "connected"
        })
        self.start = True
        gevent.spawn(self.send_uptime)
        self.kernel_func = gevent.spawn(self.send_kernel_info)

    # Run on every disconnect
    def recv_disconnect(self):
        self.start = False
        self.disconnect(silent=True)

    def send_uptime(self):
        while self.start:
            if not self.start:
                break
            self.emit('sysinfo:uptime', {'data': uptime(), 'key': 'sysinfo:uptime'})
            gevent.sleep(30)

    def send_kernel_info(self):
            try:
                self.emit('sysinfo:kernel_info', {
                    'data': kernel_info(self.supported_kernel),
                    'key': 'sysinfo:kernel_info'})
                # Send information once per connection
                self.kernel_func.kill()
            except Exception as e:
                logger.debug('kernel error')
                # Emit an event to the front end to capture error report
                self.emit('sysinfo:kernel_error', {'error': str(e)})
                self.error('unsupported_kernel', str(e))


class Application(object):
    def __init__(self):
        self.buffer = []

    def __call__(self, environ, start_response):
        path = environ['PATH_INFO'].strip('/') or 'index.html'

        if path.startswith('/static') or path == 'index.html':
            try:
                data = open(path).read()
            except Exception:
                return not_found(start_response)

            if path.endswith(".js"):
                content_type = "text/javascript"
            elif path.endswith(".css"):
                content_type = "text/css"
            elif path.endswith(".swf"):
                content_type = "application/x-shockwave-flash"
            else:
                content_type = "text/html"

            start_response('200 OK', [('Content-Type', content_type)])
            return [data]
        if path.startswith("socket.io"):
            socketio_manage(environ, {'/services': ServicesNamespace,
                                      '/sysinfo': SysinfoNamespace})



def not_found(start_response):
    start_response('404 Not Found', [])
    return ['<h1>Not found</h1>']


def main():
    logger.debug('Listening on port http://127.0.0.1:8080 and on port 10843 (flash policy server)')
    SocketIOServer(('127.0.0.1', 8001), Application(),
            resource="socket.io", policy_server=True).serve_forever()
