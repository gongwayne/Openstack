#   Copyright 2013, Red Hat, Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.

import mock
from oslo_serialization import jsonutils
import webob

from cinder import db
from cinder import test
from cinder.tests.unit.api import fakes
from cinder.tests.unit.api.v2 import stubs


def stub_snapshot_get(context, snapshot_id):
    snapshot = stubs.stub_snapshot(snapshot_id)
    if snapshot_id == 3:
        snapshot['status'] = 'error'
    elif snapshot_id == 1:
        snapshot['status'] = 'creating'
    elif snapshot_id == 7:
        snapshot['status'] = 'available'
    else:
        snapshot['status'] = 'creating'

    return snapshot


class SnapshotActionsTest(test.TestCase):

    def setUp(self):
        super(SnapshotActionsTest, self).setUp()

    @mock.patch('cinder.db.snapshot_update', autospec=True)
    @mock.patch('cinder.db.sqlalchemy.api._snapshot_get',
                side_effect=stub_snapshot_get)
    @mock.patch('cinder.db.snapshot_metadata_get', return_value=dict())
    def test_update_snapshot_status(self, metadata_get, *args):
        body = {'os-update_snapshot_status': {'status': 'available'}}
        req = webob.Request.blank('/v2/fake/snapshots/1/action')
        req.method = "POST"
        req.body = jsonutils.dump_as_bytes(body)
        req.headers["content-type"] = "application/json"

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(202, res.status_int)

    @mock.patch('cinder.db.sqlalchemy.api._snapshot_get',
                side_effect=stub_snapshot_get)
    @mock.patch('cinder.db.snapshot_metadata_get', return_value=dict())
    def test_update_snapshot_status_invalid_status(self, metadata_get, *args):
        body = {'os-update_snapshot_status': {'status': 'in-use'}}
        req = webob.Request.blank('/v2/fake/snapshots/1/action')
        req.method = "POST"
        req.body = jsonutils.dump_as_bytes(body)
        req.headers["content-type"] = "application/json"

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(400, res.status_int)

    def test_update_snapshot_status_without_status(self):
        self.stubs.Set(db, 'snapshot_get', stub_snapshot_get)
        body = {'os-update_snapshot_status': {}}
        req = webob.Request.blank('/v2/fake/snapshots/1/action')
        req.method = "POST"
        req.body = jsonutils.dump_as_bytes(body)
        req.headers["content-type"] = "application/json"

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(400, res.status_int)
