#   Copyright 2012 OpenStack Foundation
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

import uuid

from lxml import etree
from oslo_serialization import jsonutils
import webob

from cinder import context
from cinder import objects
from cinder import test
from cinder.tests.unit.api import fakes
from cinder.tests.unit import fake_volume
from cinder import volume


PROJECT_ID = '88fd1da4-f464-4a87-9ce5-26f2f40743b9'


def fake_volume_get(*args, **kwargs):
    ctx = context.RequestContext('non-admin', 'fake', False)
    vol = {
        'id': 'fake',
        'project_id': PROJECT_ID,
    }
    return fake_volume.fake_volume_obj(ctx, **vol)


def fake_volume_get_all(*args, **kwargs):
    return objects.VolumeList(objects=[fake_volume_get()])


def app():
    # no auth, just let environ['cinder.context'] pass through
    api = fakes.router.APIRouter()
    mapper = fakes.urlmap.URLMap()
    mapper['/v2'] = api
    return mapper


class VolumeTenantAttributeTest(test.TestCase):

    def setUp(self):
        super(VolumeTenantAttributeTest, self).setUp()
        self.stubs.Set(volume.api.API, 'get', fake_volume_get)
        self.stubs.Set(volume.api.API, 'get_all', fake_volume_get_all)
        self.UUID = uuid.uuid4()

    def test_get_volume_allowed(self):
        ctx = context.RequestContext('admin', 'fake', True)
        req = webob.Request.blank('/v2/fake/volumes/%s' % self.UUID)
        req.method = 'GET'
        req.environ['cinder.context'] = ctx
        res = req.get_response(app())
        vol = jsonutils.loads(res.body)['volume']
        self.assertEqual(PROJECT_ID, vol['os-vol-tenant-attr:tenant_id'])

    def test_get_volume_unallowed(self):
        ctx = context.RequestContext('non-admin', 'fake', False)
        req = webob.Request.blank('/v2/fake/volumes/%s' % self.UUID)
        req.method = 'GET'
        req.environ['cinder.context'] = ctx
        res = req.get_response(app())
        vol = jsonutils.loads(res.body)['volume']
        self.assertNotIn('os-vol-tenant-attr:tenant_id', vol)

    def test_list_detail_volumes_allowed(self):
        ctx = context.RequestContext('admin', 'fake', True)
        req = webob.Request.blank('/v2/fake/volumes/detail')
        req.method = 'GET'
        req.environ['cinder.context'] = ctx
        res = req.get_response(app())
        vol = jsonutils.loads(res.body)['volumes']
        self.assertEqual(PROJECT_ID, vol[0]['os-vol-tenant-attr:tenant_id'])

    def test_list_detail_volumes_unallowed(self):
        ctx = context.RequestContext('non-admin', 'fake', False)
        req = webob.Request.blank('/v2/fake/volumes/detail')
        req.method = 'GET'
        req.environ['cinder.context'] = ctx
        res = req.get_response(app())
        vol = jsonutils.loads(res.body)['volumes']
        self.assertNotIn('os-vol-tenant-attr:tenant_id', vol[0])

    def test_list_simple_volumes_no_tenant_id(self):
        ctx = context.RequestContext('admin', 'fake', True)
        req = webob.Request.blank('/v2/fake/volumes')
        req.method = 'GET'
        req.environ['cinder.context'] = ctx
        res = req.get_response(app())
        vol = jsonutils.loads(res.body)['volumes']
        self.assertNotIn('os-vol-tenant-attr:tenant_id', vol[0])

    def test_get_volume_xml(self):
        ctx = context.RequestContext('admin', 'fake', True)
        req = webob.Request.blank('/v2/fake/volumes/%s' % self.UUID)
        req.method = 'GET'
        req.accept = 'application/xml'
        req.environ['cinder.context'] = ctx
        res = req.get_response(app())
        vol = etree.XML(res.body)
        tenant_key = ('{http://docs.openstack.org/volume/ext/'
                      'volume_tenant_attribute/api/v2}tenant_id')
        self.assertEqual(PROJECT_ID, vol.get(tenant_key))

    def test_list_volumes_detail_xml(self):
        ctx = context.RequestContext('admin', 'fake', True)
        req = webob.Request.blank('/v2/fake/volumes/detail')
        req.method = 'GET'
        req.accept = 'application/xml'
        req.environ['cinder.context'] = ctx
        res = req.get_response(app())
        vol = list(etree.XML(res.body))[0]
        tenant_key = ('{http://docs.openstack.org/volume/ext/'
                      'volume_tenant_attribute/api/v2}tenant_id')
        self.assertEqual(PROJECT_ID, vol.get(tenant_key))