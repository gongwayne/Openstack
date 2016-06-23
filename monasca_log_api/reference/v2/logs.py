# Copyright 2015 kornicameister@gmail.com
# Copyright 2016 FUJITSU LIMITED
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import falcon

from monasca_log_api.api import headers
from monasca_log_api.api import logs_api
from monasca_log_api.reference.v2.common import log_publisher
from monasca_log_api.reference.v2.common import service
from monasca_log_api import uri_map

_DEPRECATED_INFO = ('%s has been deprecated. Please use %s.'
                    % (uri_map.V2_LOGS_URI, uri_map.V3_LOGS_URI))


# TODO(idea) perhaps add it as pipeline call right before API, seems generic
def _before_logs_post(req, res, payload, params):
    cross_tenant_id = req.get_param('tenant_id')
    tenant_id = req.get_header(*headers.X_TENANT_ID)

    if not service.is_delegate(req.get_header(*headers.X_ROLES)):
        if cross_tenant_id:
            raise falcon.HTTPForbidden(
                'Permission denied',
                'Projects %s cannot POST cross tenant metrics' % tenant_id
            )


class Logs(logs_api.LogsApi):
    """Logs Api V2."""

    VERSION = 'v2.0'

    def __init__(self):
        self._log_creator = service.LogCreator()
        self._kafka_publisher = log_publisher.LogPublisher()
        super(Logs, self).__init__()

    @falcon.before(_before_logs_post)
    @falcon.deprecated(_DEPRECATED_INFO)
    def on_post(self, req, res):
        service.Validations.validate_payload_size(req)
        service.Validations.validate_content_type(req)

        cross_tenant_id = req.get_param('tenant_id')
        tenant_id = req.get_header(*headers.X_TENANT_ID)

        log = self.get_log(request=req)
        envelope = self.get_envelope(
            log=log,
            tenant_id=tenant_id if tenant_id else cross_tenant_id
        )

        self._kafka_publisher.send_message(envelope)

        res.status = falcon.HTTP_204
        res.add_link(
            target=str(_get_v3_link(req)),
            rel='current',  # [RFC5005]
            title='V3 Logs',
            type_hint='application/json'
        )
        res.append_header('DEPRECATED', 'true')

    def get_envelope(self, log, tenant_id):
        return self._log_creator.new_log_envelope(
            log_object=log,
            tenant_id=tenant_id
        )

    def get_log(self, request):
        return self._log_creator.new_log(
            application_type=request.get_header(*headers.X_APPLICATION_TYPE),
            dimensions=request.get_header(*headers.X_DIMENSIONS),
            payload=request.stream,
            content_type=request.content_type
        )


def _get_v3_link(req):
    self_uri = req.uri.decode('UTF-8')
    base_uri = self_uri.replace(req.relative_uri, '')
    return '%s%s' % (base_uri, uri_map.V3_LOGS_URI)
