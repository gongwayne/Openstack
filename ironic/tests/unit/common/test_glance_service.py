# Copyright 2013 Hewlett-Packard Development Company, L.P.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


import datetime
import time

from glanceclient import client as glance_client
from glanceclient import exc as glance_exc
import mock
from oslo_config import cfg
from oslo_context import context
from oslo_serialization import jsonutils
from oslo_utils import uuidutils
from six.moves.urllib import parse as urlparse
import testtools

from ironic.common import exception
from ironic.common.glance_service import base_image_service
from ironic.common.glance_service import service_utils
from ironic.common.glance_service.v2 import image_service as glance_v2
from ironic.common import image_service as service
from ironic.tests import base
from ironic.tests.unit import stubs


CONF = cfg.CONF


class NullWriter(object):
    """Used to test ImageService.get which takes a writer object."""

    def write(self, *arg, **kwargs):
        pass


class TestGlanceSerializer(testtools.TestCase):
    def test_serialize(self):
        metadata = {'name': 'image1',
                    'is_public': True,
                    'foo': 'bar',
                    'properties': {
                        'prop1': 'propvalue1',
                        'mappings': [
                            {'virtual': 'aaa',
                             'device': 'bbb'},
                            {'virtual': 'xxx',
                             'device': 'yyy'}],
                        'block_device_mapping': [
                            {'virtual_device': 'fake',
                             'device_name': '/dev/fake'},
                            {'virtual_device': 'ephemeral0',
                             'device_name': '/dev/fake0'}]}}

        converted_expected = {
            'name': 'image1',
            'is_public': True,
            'foo': 'bar',
            'properties': {'prop1': 'propvalue1'}
        }
        converted = service_utils._convert(metadata, 'to')
        self.assertEqual(metadata,
                         service_utils._convert(converted, 'from'))
        # Fields that rely on dict ordering can't be compared as text
        mappings = jsonutils.loads(converted['properties']
                                   .pop('mappings'))
        self.assertEqual([{"device": "bbb", "virtual": "aaa"},
                          {"device": "yyy", "virtual": "xxx"}],
                         mappings)
        bd_mapping = jsonutils.loads(converted['properties']
                                     .pop('block_device_mapping'))
        self.assertEqual([{"virtual_device": "fake",
                           "device_name": "/dev/fake"},
                          {"virtual_device": "ephemeral0",
                           "device_name": "/dev/fake0"}],
                         bd_mapping)
        # Compare the remaining
        self.assertEqual(converted_expected, converted)


class TestGlanceImageService(base.TestCase):
    NOW_GLANCE_OLD_FORMAT = "2010-10-11T10:30:22"
    NOW_GLANCE_FORMAT = "2010-10-11T10:30:22.000000"

    NOW_DATETIME = datetime.datetime(2010, 10, 11, 10, 30, 22)

    def setUp(self):
        super(TestGlanceImageService, self).setUp()
        client = stubs.StubGlanceClient()
        self.context = context.RequestContext(auth_token=True)
        self.context.user_id = 'fake'
        self.context.project_id = 'fake'
        self.service = service.GlanceImageService(client, 1, self.context)

        self.config(glance_host='localhost', group='glance')
        try:
            self.config(auth_strategy='keystone', group='glance')
        except Exception:
            opts = [
                cfg.StrOpt('auth_strategy', default='keystone'),
            ]
            CONF.register_opts(opts)

        return

    @staticmethod
    def _make_fixture(**kwargs):
        fixture = {'name': None,
                   'properties': {},
                   'status': None,
                   'is_public': None}
        fixture.update(kwargs)
        return fixture

    @property
    def endpoint(self):
        # For glanceclient versions >= 0.13, the endpoint is located
        # under http_client (blueprint common-client-library-2)
        # I5addc38eb2e2dd0be91b566fda7c0d81787ffa75
        # Test both options to keep backward compatibility
        if getattr(self.service.client, 'endpoint', None):
            endpoint = self.service.client.endpoint
        else:
            endpoint = self.service.client.http_client.endpoint
        return endpoint

    def _make_datetime_fixture(self):
        return self._make_fixture(created_at=self.NOW_GLANCE_FORMAT,
                                  updated_at=self.NOW_GLANCE_FORMAT,
                                  deleted_at=self.NOW_GLANCE_FORMAT)

    def test_create_with_instance_id(self):
        # Ensure instance_id is persisted as an image-property.
        fixture = {'name': 'test image',
                   'is_public': False,
                   'properties': {'instance_id': '42', 'user_id': 'fake'}}
        image_id = self.service.create(fixture)['id']
        image_meta = self.service.show(image_id)
        expected = {
            'id': image_id,
            'name': 'test image',
            'is_public': False,
            'size': None,
            'min_disk': None,
            'min_ram': None,
            'disk_format': None,
            'container_format': None,
            'checksum': None,
            'created_at': self.NOW_DATETIME,
            'updated_at': self.NOW_DATETIME,
            'deleted_at': None,
            'deleted': None,
            'status': None,
            'properties': {'instance_id': '42', 'user_id': 'fake'},
            'owner': None,
        }

        self.assertDictEqual(expected, image_meta)

        image_metas = self.service.detail()
        self.assertDictEqual(expected, image_metas[0])

    def test_create_without_instance_id(self):
        """Test creating an image without an instance ID.

        Ensure we can create an image without having to specify an
        instance_id. Public images are an example of an image not tied to an
        instance.
        """
        fixture = {'name': 'test image', 'is_public': False}
        image_id = self.service.create(fixture)['id']

        expected = {
            'id': image_id,
            'name': 'test image',
            'is_public': False,
            'size': None,
            'min_disk': None,
            'min_ram': None,
            'disk_format': None,
            'container_format': None,
            'checksum': None,
            'created_at': self.NOW_DATETIME,
            'updated_at': self.NOW_DATETIME,
            'deleted_at': None,
            'deleted': None,
            'status': None,
            'properties': {},
            'owner': None,
        }
        actual = self.service.show(image_id)
        self.assertDictEqual(expected, actual)

    def test_create(self):
        fixture = self._make_fixture(name='test image')
        num_images = len(self.service.detail())
        image_id = self.service.create(fixture)['id']

        self.assertIsNotNone(image_id)
        self.assertEqual(
            num_images + 1, len(self.service.detail()))

    def test_create_and_show_non_existing_image(self):
        fixture = self._make_fixture(name='test image')
        image_id = self.service.create(fixture)['id']

        self.assertIsNotNone(image_id)
        self.assertRaises(exception.ImageNotFound,
                          self.service.show,
                          'bad image id')

    def test_detail_private_image(self):
        fixture = self._make_fixture(name='test image')
        fixture['is_public'] = False
        properties = {'owner_id': 'proj1'}
        fixture['properties'] = properties

        self.service.create(fixture)['id']

        proj = self.context.project_id
        self.context.project_id = 'proj1'

        image_metas = self.service.detail()

        self.context.project_id = proj

        self.assertEqual(1, len(image_metas))
        self.assertEqual('test image', image_metas[0]['name'])
        self.assertFalse(image_metas[0]['is_public'])

    def test_detail_marker(self):
        fixtures = []
        ids = []
        for i in range(10):
            fixture = self._make_fixture(name='TestImage %d' % (i))
            fixtures.append(fixture)
            ids.append(self.service.create(fixture)['id'])

        image_metas = self.service.detail(marker=ids[1])
        self.assertEqual(8, len(image_metas))
        i = 2
        for meta in image_metas:
            expected = {
                'id': ids[i],
                'status': None,
                'is_public': None,
                'name': 'TestImage %d' % (i),
                'properties': {},
                'size': None,
                'min_disk': None,
                'min_ram': None,
                'disk_format': None,
                'container_format': None,
                'checksum': None,
                'created_at': self.NOW_DATETIME,
                'updated_at': self.NOW_DATETIME,
                'deleted_at': None,
                'deleted': None,
                'owner': None,
            }

            self.assertDictEqual(expected, meta)
            i = i + 1

    def test_detail_limit(self):
        fixtures = []
        ids = []
        for i in range(10):
            fixture = self._make_fixture(name='TestImage %d' % (i))
            fixtures.append(fixture)
            ids.append(self.service.create(fixture)['id'])

        image_metas = self.service.detail(limit=5)
        self.assertEqual(5, len(image_metas))

    def test_detail_default_limit(self):
        fixtures = []
        ids = []
        for i in range(10):
            fixture = self._make_fixture(name='TestImage %d' % (i))
            fixtures.append(fixture)
            ids.append(self.service.create(fixture)['id'])

        image_metas = self.service.detail()
        for i, meta in enumerate(image_metas):
            self.assertEqual(meta['name'], 'TestImage %d' % (i))

    def test_detail_marker_and_limit(self):
        fixtures = []
        ids = []
        for i in range(10):
            fixture = self._make_fixture(name='TestImage %d' % (i))
            fixtures.append(fixture)
            ids.append(self.service.create(fixture)['id'])

        image_metas = self.service.detail(marker=ids[3], limit=5)
        self.assertEqual(5, len(image_metas))
        i = 4
        for meta in image_metas:
            expected = {
                'id': ids[i],
                'status': None,
                'is_public': None,
                'name': 'TestImage %d' % (i),
                'properties': {},
                'size': None,
                'min_disk': None,
                'min_ram': None,
                'disk_format': None,
                'container_format': None,
                'checksum': None,
                'created_at': self.NOW_DATETIME,
                'updated_at': self.NOW_DATETIME,
                'deleted_at': None,
                'deleted': None,
                'owner': None,
            }
            self.assertDictEqual(expected, meta)
            i = i + 1

    def test_detail_invalid_marker(self):
        fixtures = []
        ids = []
        for i in range(10):
            fixture = self._make_fixture(name='TestImage %d' % (i))
            fixtures.append(fixture)
            ids.append(self.service.create(fixture)['id'])

        self.assertRaises(exception.Invalid, self.service.detail,
                          marker='invalidmarker')

    def test_update(self):
        fixture = self._make_fixture(name='test image')
        image = self.service.create(fixture)
        image_id = image['id']
        fixture['name'] = 'new image name'
        self.service.update(image_id, fixture)

        new_image_data = self.service.show(image_id)
        self.assertEqual('new image name', new_image_data['name'])

    def test_delete(self):
        fixture1 = self._make_fixture(name='test image 1')
        fixture2 = self._make_fixture(name='test image 2')
        fixtures = [fixture1, fixture2]

        num_images = len(self.service.detail())
        self.assertEqual(0, num_images)

        ids = []
        for fixture in fixtures:
            new_id = self.service.create(fixture)['id']
            ids.append(new_id)

        num_images = len(self.service.detail())
        self.assertEqual(2, num_images)

        self.service.delete(ids[0])
        # When you delete an image from glance, it sets the status to DELETED
        # and doesn't actually remove the image.

        # Check the image is still there.
        num_images = len(self.service.detail())
        self.assertEqual(2, num_images)

        # Check the image is marked as deleted.
        num_images = len([x for x in self.service.detail()
                          if not x['deleted']])
        self.assertEqual(1, num_images)

    def test_show_passes_through_to_client(self):
        fixture = self._make_fixture(name='image1', is_public=True)
        image_id = self.service.create(fixture)['id']

        image_meta = self.service.show(image_id)
        expected = {
            'id': image_id,
            'name': 'image1',
            'is_public': True,
            'size': None,
            'min_disk': None,
            'min_ram': None,
            'disk_format': None,
            'container_format': None,
            'checksum': None,
            'created_at': self.NOW_DATETIME,
            'updated_at': self.NOW_DATETIME,
            'deleted_at': None,
            'deleted': None,
            'status': None,
            'properties': {},
            'owner': None,
        }
        self.assertEqual(expected, image_meta)

    def test_show_raises_when_no_authtoken_in_the_context(self):
        fixture = self._make_fixture(name='image1',
                                     is_public=False,
                                     properties={'one': 'two'})
        image_id = self.service.create(fixture)['id']
        self.context.auth_token = False
        self.assertRaises(exception.ImageNotFound,
                          self.service.show,
                          image_id)

    def test_detail_passes_through_to_client(self):
        fixture = self._make_fixture(name='image10', is_public=True)
        image_id = self.service.create(fixture)['id']
        image_metas = self.service.detail()
        expected = [
            {
                'id': image_id,
                'name': 'image10',
                'is_public': True,
                'size': None,
                'min_disk': None,
                'min_ram': None,
                'disk_format': None,
                'container_format': None,
                'checksum': None,
                'created_at': self.NOW_DATETIME,
                'updated_at': self.NOW_DATETIME,
                'deleted_at': None,
                'deleted': None,
                'status': None,
                'properties': {},
                'owner': None,
            },
        ]
        self.assertEqual(expected, image_metas)

    def test_show_makes_datetimes(self):
        fixture = self._make_datetime_fixture()
        image_id = self.service.create(fixture)['id']
        image_meta = self.service.show(image_id)
        self.assertEqual(self.NOW_DATETIME, image_meta['created_at'])
        self.assertEqual(self.NOW_DATETIME, image_meta['updated_at'])

    def test_detail_makes_datetimes(self):
        fixture = self._make_datetime_fixture()
        self.service.create(fixture)
        image_meta = self.service.detail()[0]
        self.assertEqual(self.NOW_DATETIME, image_meta['created_at'])
        self.assertEqual(self.NOW_DATETIME, image_meta['updated_at'])

    @mock.patch.object(time, 'sleep', autospec=True)
    def test_download_with_retries(self, mock_sleep):
        tries = [0]

        class MyGlanceStubClient(stubs.StubGlanceClient):
            """A client that fails the first time, then succeeds."""
            def get(self, image_id):
                if tries[0] == 0:
                    tries[0] = 1
                    raise glance_exc.ServiceUnavailable('')
                else:
                    return {}

        stub_client = MyGlanceStubClient()
        stub_context = context.RequestContext(auth_token=True)
        stub_context.user_id = 'fake'
        stub_context.project_id = 'fake'
        stub_service = service.GlanceImageService(stub_client, 1, stub_context)
        image_id = 1  # doesn't matter
        writer = NullWriter()

        # When retries are disabled, we should get an exception
        self.config(glance_num_retries=0, group='glance')
        self.assertRaises(exception.GlanceConnectionFailed,
                          stub_service.download, image_id, writer)

        # Now lets enable retries. No exception should happen now.
        tries = [0]
        self.config(glance_num_retries=1, group='glance')
        stub_service.download(image_id, writer)
        self.assertTrue(mock_sleep.called)

    @mock.patch('sendfile.sendfile', autospec=True)
    @mock.patch('os.path.getsize', autospec=True)
    @mock.patch('%s.open' % __name__, new=mock.mock_open(), create=True)
    def test_download_file_url(self, mock_getsize, mock_sendfile):
        # NOTE: only in v2 API
        class MyGlanceStubClient(stubs.StubGlanceClient):

            """A client that returns a file url."""

            s_tmpfname = '/whatever/source'

            def get(self, image_id):
                return type('GlanceTestDirectUrlMeta', (object,),
                            {'direct_url': 'file://%s' + self.s_tmpfname})

        stub_context = context.RequestContext(auth_token=True)
        stub_context.user_id = 'fake'
        stub_context.project_id = 'fake'
        stub_client = MyGlanceStubClient()

        stub_service = service.GlanceImageService(stub_client,
                                                  context=stub_context,
                                                  version=2)
        image_id = 1  # doesn't matter

        self.config(allowed_direct_url_schemes=['file'], group='glance')

        # patching open in base_image_service module namespace
        # to make call-spec assertions
        with mock.patch('ironic.common.glance_service.base_image_service.open',
                        new=mock.mock_open(), create=True) as mock_ironic_open:
            with open('/whatever/target', 'w') as mock_target_fd:
                stub_service.download(image_id, mock_target_fd)

        # assert the image data was neither read nor written
        # but rather sendfiled
        mock_ironic_open.assert_called_once_with(MyGlanceStubClient.s_tmpfname,
                                                 'r')
        mock_source_fd = mock_ironic_open()
        self.assertFalse(mock_source_fd.read.called)
        self.assertFalse(mock_target_fd.write.called)
        mock_sendfile.assert_called_once_with(
            mock_target_fd.fileno(),
            mock_source_fd.fileno(),
            0,
            mock_getsize(MyGlanceStubClient.s_tmpfname))

    def test_client_forbidden_converts_to_imagenotauthed(self):
        class MyGlanceStubClient(stubs.StubGlanceClient):
            """A client that raises a Forbidden exception."""
            def get(self, image_id):
                raise glance_exc.Forbidden(image_id)

        stub_client = MyGlanceStubClient()
        stub_context = context.RequestContext(auth_token=True)
        stub_context.user_id = 'fake'
        stub_context.project_id = 'fake'
        stub_service = service.GlanceImageService(stub_client, 1, stub_context)
        image_id = 1  # doesn't matter
        writer = NullWriter()
        self.assertRaises(exception.ImageNotAuthorized, stub_service.download,
                          image_id, writer)

    def test_client_httpforbidden_converts_to_imagenotauthed(self):
        class MyGlanceStubClient(stubs.StubGlanceClient):
            """A client that raises a HTTPForbidden exception."""
            def get(self, image_id):
                raise glance_exc.HTTPForbidden(image_id)

        stub_client = MyGlanceStubClient()
        stub_context = context.RequestContext(auth_token=True)
        stub_context.user_id = 'fake'
        stub_context.project_id = 'fake'
        stub_service = service.GlanceImageService(stub_client, 1, stub_context)
        image_id = 1  # doesn't matter
        writer = NullWriter()
        self.assertRaises(exception.ImageNotAuthorized, stub_service.download,
                          image_id, writer)

    def test_client_notfound_converts_to_imagenotfound(self):
        class MyGlanceStubClient(stubs.StubGlanceClient):
            """A client that raises a NotFound exception."""
            def get(self, image_id):
                raise glance_exc.NotFound(image_id)

        stub_client = MyGlanceStubClient()
        stub_context = context.RequestContext(auth_token=True)
        stub_context.user_id = 'fake'
        stub_context.project_id = 'fake'
        stub_service = service.GlanceImageService(stub_client, 1, stub_context)
        image_id = 1  # doesn't matter
        writer = NullWriter()
        self.assertRaises(exception.ImageNotFound, stub_service.download,
                          image_id, writer)

    def test_client_httpnotfound_converts_to_imagenotfound(self):
        class MyGlanceStubClient(stubs.StubGlanceClient):
            """A client that raises a HTTPNotFound exception."""
            def get(self, image_id):
                raise glance_exc.HTTPNotFound(image_id)

        stub_client = MyGlanceStubClient()
        stub_context = context.RequestContext(auth_token=True)
        stub_context.user_id = 'fake'
        stub_context.project_id = 'fake'
        stub_service = service.GlanceImageService(stub_client, 1, stub_context)
        image_id = 1  # doesn't matter
        writer = NullWriter()
        self.assertRaises(exception.ImageNotFound, stub_service.download,
                          image_id, writer)

    def test_check_image_service_client_set(self):
        def func(self):
            return True

        self.service.client = True

        wrapped_func = base_image_service.check_image_service(func)
        self.assertTrue(wrapped_func(self.service))

    @mock.patch.object(glance_client, 'Client', autospec=True)
    def test_check_image_service__no_client_set_http(self, mock_gclient):
        def func(service, *args, **kwargs):
            return (self.endpoint, args, kwargs)

        endpoint = 'http://123.123.123.123:9292'
        mock_gclient.return_value.endpoint = endpoint
        self.service.client = None

        params = {'image_href': '%s/image_uuid' % endpoint}
        self.config(auth_strategy='keystone', group='glance')
        wrapped_func = base_image_service.check_image_service(func)
        self.assertEqual((endpoint, (), params),
                         wrapped_func(self.service, **params))
        mock_gclient.assert_called_once_with(
            1, endpoint,
            **{'insecure': CONF.glance.glance_api_insecure,
               'token': self.context.auth_token})

    @mock.patch.object(glance_client, 'Client', autospec=True)
    def test_get_image_service__no_client_set_https_insecure(self,
                                                             mock_gclient):
        def func(service, *args, **kwargs):
            return (self.endpoint, args, kwargs)

        endpoint = 'https://123.123.123.123:9292'
        mock_gclient.return_value.endpoint = endpoint
        self.service.client = None

        params = {'image_href': '%s/image_uuid' % endpoint}
        self.config(auth_strategy='keystone', group='glance')
        self.config(glance_api_insecure=True, group='glance')
        wrapped_func = base_image_service.check_image_service(func)

        self.assertEqual((endpoint, (), params),
                         wrapped_func(self.service, **params))
        mock_gclient.assert_called_once_with(
            1, endpoint,
            **{'insecure': CONF.glance.glance_api_insecure,
               'token': self.context.auth_token})

    @mock.patch.object(glance_client, 'Client', autospec=True)
    def test_get_image_service__no_client_set_https_secure(self, mock_gclient):
        def func(service, *args, **kwargs):
            return (self.endpoint, args, kwargs)

        endpoint = 'https://123.123.123.123:9292'
        mock_gclient.return_value.endpoint = endpoint
        self.service.client = None

        params = {'image_href': '%s/image_uuid' % endpoint}
        self.config(auth_strategy='keystone', group='glance')
        self.config(glance_api_insecure=False, group='glance')
        self.config(glance_cafile='/path/to/certfile', group='glance')
        wrapped_func = base_image_service.check_image_service(func)

        self.assertEqual((endpoint, (), params),
                         wrapped_func(self.service, **params))
        mock_gclient.assert_called_once_with(
            1, endpoint,
            **{'cacert': CONF.glance.glance_cafile,
               'insecure': CONF.glance.glance_api_insecure,
               'token': self.context.auth_token})


def _create_failing_glance_client(info):
    class MyGlanceStubClient(stubs.StubGlanceClient):
        """A client that fails the first time, then succeeds."""
        def get(self, image_id):
            info['num_calls'] += 1
            if info['num_calls'] == 1:
                raise glance_exc.ServiceUnavailable('')
            return {}

    return MyGlanceStubClient()


class TestGlanceSwiftTempURL(base.TestCase):
    def setUp(self):
        super(TestGlanceSwiftTempURL, self).setUp()
        client = stubs.StubGlanceClient()
        self.context = context.RequestContext()
        self.context.auth_token = 'fake'
        self.service = service.GlanceImageService(client, 2, self.context)
        self.config(swift_temp_url_key='correcthorsebatterystaple',
                    group='glance')
        self.config(swift_endpoint_url='https://swift.example.com',
                    group='glance')
        self.config(swift_account='AUTH_a422b2-91f3-2f46-74b7-d7c9e8958f5d30',
                    group='glance')
        self.config(swift_api_version='v1',
                    group='glance')
        self.config(swift_container='glance',
                    group='glance')
        self.config(swift_temp_url_duration=1200,
                    group='glance')
        self.config(swift_store_multiple_containers_seed=0,
                    group='glance')
        self.config()
        self.fake_image = {
            'id': '757274c4-2856-4bd2-bb20-9a4a231e187b'
        }

    @mock.patch('swiftclient.utils.generate_temp_url', autospec=True)
    def test_swift_temp_url(self, tempurl_mock):

        path = ('/v1/AUTH_a422b2-91f3-2f46-74b7-d7c9e8958f5d30'
                '/glance'
                '/757274c4-2856-4bd2-bb20-9a4a231e187b')
        tempurl_mock.return_value = (
            path + '?temp_url_sig=hmacsig&temp_url_expires=1400001200')

        self.service._validate_temp_url_config = mock.Mock()

        temp_url = self.service.swift_temp_url(image_info=self.fake_image)

        self.assertEqual(CONF.glance.swift_endpoint_url
                         + tempurl_mock.return_value,
                         temp_url)
        tempurl_mock.assert_called_with(
            path=path,
            seconds=CONF.glance.swift_temp_url_duration,
            key=CONF.glance.swift_temp_url_key,
            method='GET')

    @mock.patch('swiftclient.utils.generate_temp_url', autospec=True)
    def test_swift_temp_url_invalid_image_info(self, tempurl_mock):
        self.service._validate_temp_url_config = mock.Mock()
        image_info = {}
        self.assertRaises(exception.ImageUnacceptable,
                          self.service.swift_temp_url, image_info)
        image_info = {'id': 'not an id'}
        self.assertRaises(exception.ImageUnacceptable,
                          self.service.swift_temp_url, image_info)
        self.assertFalse(tempurl_mock.called)

    @mock.patch('swiftclient.utils.generate_temp_url', autospec=True)
    def test_swift_temp_url_radosgw(self, tempurl_mock):
        self.config(temp_url_endpoint_type='radosgw', group='glance')
        path = ('/v1'
                '/glance'
                '/757274c4-2856-4bd2-bb20-9a4a231e187b')
        tempurl_mock.return_value = (
            path + '?temp_url_sig=hmacsig&temp_url_expires=1400001200')

        self.service._validate_temp_url_config = mock.Mock()

        temp_url = self.service.swift_temp_url(image_info=self.fake_image)

        self.assertEqual(
            (urlparse.urljoin(CONF.glance.swift_endpoint_url, 'swift') +
             tempurl_mock.return_value),
            temp_url)
        tempurl_mock.assert_called_with(
            path=path,
            seconds=CONF.glance.swift_temp_url_duration,
            key=CONF.glance.swift_temp_url_key,
            method='GET')

    @mock.patch('swiftclient.utils.generate_temp_url', autospec=True)
    def test_swift_temp_url_radosgw_endpoint_with_swift(self, tempurl_mock):
        self.config(swift_endpoint_url='https://swift.radosgw.com/swift',
                    group='glance')
        self.config(temp_url_endpoint_type='radosgw', group='glance')
        path = ('/v1'
                '/glance'
                '/757274c4-2856-4bd2-bb20-9a4a231e187b')
        tempurl_mock.return_value = (
            path + '?temp_url_sig=hmacsig&temp_url_expires=1400001200')

        self.service._validate_temp_url_config = mock.Mock()

        temp_url = self.service.swift_temp_url(image_info=self.fake_image)

        self.assertEqual(
            CONF.glance.swift_endpoint_url + tempurl_mock.return_value,
            temp_url)
        tempurl_mock.assert_called_with(
            path=path,
            seconds=CONF.glance.swift_temp_url_duration,
            key=CONF.glance.swift_temp_url_key,
            method='GET')

    @mock.patch('swiftclient.utils.generate_temp_url', autospec=True)
    def test_swift_temp_url_radosgw_endpoint_invalid(self, tempurl_mock):
        self.config(swift_endpoint_url='https://swift.radosgw.com/eggs/',
                    group='glance')
        self.config(temp_url_endpoint_type='radosgw', group='glance')
        self.service._validate_temp_url_config = mock.Mock()

        self.assertRaises(exception.InvalidParameterValue,
                          self.service.swift_temp_url,
                          self.fake_image)
        self.assertFalse(tempurl_mock.called)

    @mock.patch('swiftclient.utils.generate_temp_url', autospec=True)
    def test_swift_temp_url_multiple_containers(self, tempurl_mock):

        self.config(swift_store_multiple_containers_seed=8,
                    group='glance')

        path = ('/v1/AUTH_a422b2-91f3-2f46-74b7-d7c9e8958f5d30'
                '/glance_757274c4'
                '/757274c4-2856-4bd2-bb20-9a4a231e187b')
        tempurl_mock.return_value = (
            path + '?temp_url_sig=hmacsig&temp_url_expires=1400001200')

        self.service._validate_temp_url_config = mock.Mock()

        temp_url = self.service.swift_temp_url(image_info=self.fake_image)

        self.assertEqual(CONF.glance.swift_endpoint_url
                         + tempurl_mock.return_value,
                         temp_url)
        tempurl_mock.assert_called_with(
            path=path,
            seconds=CONF.glance.swift_temp_url_duration,
            key=CONF.glance.swift_temp_url_key,
            method='GET')

    def test_swift_temp_url_url_bad_no_info(self):
        self.assertRaises(exception.ImageUnacceptable,
                          self.service.swift_temp_url,
                          image_info={})

    def test__validate_temp_url_config(self):
        self.service._validate_temp_url_config()

    def test__validate_temp_url_key_exception(self):
        self.config(swift_temp_url_key=None, group='glance')
        self.assertRaises(exception.MissingParameterValue,
                          self.service._validate_temp_url_config)

    def test__validate_temp_url_endpoint_config_exception(self):
        self.config(swift_endpoint_url=None, group='glance')
        self.assertRaises(exception.MissingParameterValue,
                          self.service._validate_temp_url_config)

    def test__validate_temp_url_account_exception(self):
        self.config(swift_account=None, group='glance')
        self.assertRaises(exception.MissingParameterValue,
                          self.service._validate_temp_url_config)

    def test__validate_temp_url_no_account_exception_radosgw(self):
        self.config(swift_account=None, group='glance')
        self.config(temp_url_endpoint_type='radosgw', group='glance')
        self.service._validate_temp_url_config()

    def test__validate_temp_url_endpoint_less_than_download_delay(self):
        self.config(swift_temp_url_expected_download_start_delay=1000,
                    group='glance')
        self.config(swift_temp_url_duration=15,
                    group='glance')
        self.assertRaises(exception.InvalidParameterValue,
                          self.service._validate_temp_url_config)

    def test__validate_temp_url_multiple_containers(self):
        self.config(swift_store_multiple_containers_seed=-1,
                    group='glance')
        self.assertRaises(exception.InvalidParameterValue,
                          self.service._validate_temp_url_config)
        self.config(swift_store_multiple_containers_seed=None,
                    group='glance')
        self.assertRaises(exception.InvalidParameterValue,
                          self.service._validate_temp_url_config)
        self.config(swift_store_multiple_containers_seed=33,
                    group='glance')
        self.assertRaises(exception.InvalidParameterValue,
                          self.service._validate_temp_url_config)


class TestSwiftTempUrlCache(base.TestCase):

    def setUp(self):
        super(TestSwiftTempUrlCache, self).setUp()
        client = stubs.StubGlanceClient()
        self.context = context.RequestContext()
        self.context.auth_token = 'fake'
        self.config(swift_temp_url_expected_download_start_delay=100,
                    group='glance')
        self.config(swift_temp_url_key='correcthorsebatterystaple',
                    group='glance')
        self.config(swift_endpoint_url='https://swift.example.com',
                    group='glance')
        self.config(swift_account='AUTH_a422b2-91f3-2f46-74b7-d7c9e8958f5d30',
                    group='glance')
        self.config(swift_api_version='v1',
                    group='glance')
        self.config(swift_container='glance',
                    group='glance')
        self.config(swift_temp_url_duration=1200,
                    group='glance')
        self.config(swift_temp_url_cache_enabled=True,
                    group='glance')
        self.config(swift_store_multiple_containers_seed=0,
                    group='glance')
        self.glance_service = service.GlanceImageService(client, version=2,
                                                         context=self.context)

    @mock.patch('swiftclient.utils.generate_temp_url', autospec=True)
    def test_add_items_to_cache(self, tempurl_mock):
        fake_image = {
            'id': uuidutils.generate_uuid()
        }

        path = ('/v1/AUTH_a422b2-91f3-2f46-74b7-d7c9e8958f5d30'
                '/glance'
                '/%s' % fake_image['id'])
        exp_time = int(time.time()) + 1200
        tempurl_mock.return_value = (
            path + '?temp_url_sig=hmacsig&temp_url_expires=%s' % exp_time)

        cleanup_mock = mock.Mock()
        self.glance_service._remove_expired_items_from_cache = cleanup_mock
        self.glance_service._validate_temp_url_config = mock.Mock()

        temp_url = self.glance_service.swift_temp_url(
            image_info=fake_image)

        self.assertEqual(CONF.glance.swift_endpoint_url +
                         tempurl_mock.return_value,
                         temp_url)
        cleanup_mock.assert_called_once_with()
        tempurl_mock.assert_called_with(
            path=path,
            seconds=CONF.glance.swift_temp_url_duration,
            key=CONF.glance.swift_temp_url_key,
            method='GET')
        self.assertEqual((temp_url, exp_time),
                         self.glance_service._cache[fake_image['id']])

    @mock.patch('swiftclient.utils.generate_temp_url', autospec=True)
    def test_return_cached_tempurl(self, tempurl_mock):
        fake_image = {
            'id': uuidutils.generate_uuid()
        }

        exp_time = int(time.time()) + 1200
        temp_url = CONF.glance.swift_endpoint_url + (
            '/v1/AUTH_a422b2-91f3-2f46-74b7-d7c9e8958f5d30'
            '/glance'
            '/%(uuid)s'
            '?temp_url_sig=hmacsig&temp_url_expires=%(exp_time)s' %
            {'uuid': fake_image['id'], 'exp_time': exp_time}
        )
        self.glance_service._cache[fake_image['id']] = (
            glance_v2.TempUrlCacheElement(url=temp_url,
                                          url_expires_at=exp_time)
        )

        cleanup_mock = mock.Mock()
        self.glance_service._remove_expired_items_from_cache = cleanup_mock
        self.glance_service._validate_temp_url_config = mock.Mock()

        self.assertEqual(
            temp_url, self.glance_service.swift_temp_url(image_info=fake_image)
        )

        cleanup_mock.assert_called_once_with()
        self.assertFalse(tempurl_mock.called)

    @mock.patch('swiftclient.utils.generate_temp_url', autospec=True)
    def test_do_not_return_expired_tempurls(self, tempurl_mock):
        fake_image = {
            'id': uuidutils.generate_uuid()
        }
        old_exp_time = int(time.time()) + 99
        path = (
            '/v1/AUTH_a422b2-91f3-2f46-74b7-d7c9e8958f5d30'
            '/glance'
            '/%s' % fake_image['id']
        )
        query = '?temp_url_sig=hmacsig&temp_url_expires=%s'
        self.glance_service._cache[fake_image['id']] = (
            glance_v2.TempUrlCacheElement(
                url=(CONF.glance.swift_endpoint_url + path +
                     query % old_exp_time),
                url_expires_at=old_exp_time)
        )

        new_exp_time = int(time.time()) + 1200
        tempurl_mock.return_value = (
            path + query % new_exp_time)

        self.glance_service._validate_temp_url_config = mock.Mock()

        fresh_temp_url = self.glance_service.swift_temp_url(
            image_info=fake_image)

        self.assertEqual(CONF.glance.swift_endpoint_url +
                         tempurl_mock.return_value,
                         fresh_temp_url)
        tempurl_mock.assert_called_with(
            path=path,
            seconds=CONF.glance.swift_temp_url_duration,
            key=CONF.glance.swift_temp_url_key,
            method='GET')
        self.assertEqual(
            (fresh_temp_url, new_exp_time),
            self.glance_service._cache[fake_image['id']])

    def test_remove_expired_items_from_cache(self):
        expired_items = {
            uuidutils.generate_uuid(): glance_v2.TempUrlCacheElement(
                'fake-url-1',
                int(time.time()) - 10
            ),
            uuidutils.generate_uuid(): glance_v2.TempUrlCacheElement(
                'fake-url-2',
                int(time.time()) + 90  # Agent won't be able to start in time
            )
        }
        valid_items = {
            uuidutils.generate_uuid(): glance_v2.TempUrlCacheElement(
                'fake-url-3',
                int(time.time()) + 1000
            ),
            uuidutils.generate_uuid(): glance_v2.TempUrlCacheElement(
                'fake-url-4',
                int(time.time()) + 2000
            )
        }
        self.glance_service._cache.update(expired_items)
        self.glance_service._cache.update(valid_items)
        self.glance_service._remove_expired_items_from_cache()
        for uuid in valid_items:
            self.assertEqual(valid_items[uuid],
                             self.glance_service._cache[uuid])
        for uuid in expired_items:
            self.assertNotIn(uuid, self.glance_service._cache)

    @mock.patch('swiftclient.utils.generate_temp_url', autospec=True)
    def _test__generate_temp_url(self, fake_image, tempurl_mock):
        path = ('/v1/AUTH_a422b2-91f3-2f46-74b7-d7c9e8958f5d30'
                '/glance'
                '/%s' % fake_image['id'])
        tempurl_mock.return_value = (
            path + '?temp_url_sig=hmacsig&temp_url_expires=1400001200')

        self.glance_service._validate_temp_url_config = mock.Mock()

        temp_url = self.glance_service._generate_temp_url(
            path, seconds=CONF.glance.swift_temp_url_duration,
            key=CONF.glance.swift_temp_url_key, method='GET',
            endpoint=CONF.glance.swift_endpoint_url,
            image_id=fake_image['id']
        )

        self.assertEqual(CONF.glance.swift_endpoint_url +
                         tempurl_mock.return_value,
                         temp_url)
        tempurl_mock.assert_called_with(
            path=path,
            seconds=CONF.glance.swift_temp_url_duration,
            key=CONF.glance.swift_temp_url_key,
            method='GET')

    def test_swift_temp_url_cache_enabled(self):
        fake_image = {
            'id': uuidutils.generate_uuid()
        }
        rm_expired = mock.Mock()
        self.glance_service._remove_expired_items_from_cache = rm_expired
        self._test__generate_temp_url(fake_image)
        rm_expired.assert_called_once_with()
        self.assertIn(fake_image['id'], self.glance_service._cache)

    def test_swift_temp_url_cache_disabled(self):
        self.config(swift_temp_url_cache_enabled=False,
                    group='glance')
        fake_image = {
            'id': uuidutils.generate_uuid()
        }
        rm_expired = mock.Mock()
        self.glance_service._remove_expired_items_from_cache = rm_expired
        self._test__generate_temp_url(fake_image)
        self.assertFalse(rm_expired.called)
        self.assertNotIn(fake_image['id'], self.glance_service._cache)


class TestGlanceUrl(base.TestCase):

    def test_generate_glance_http_url(self):
        self.config(glance_host="127.0.0.1", group='glance')
        generated_url = service_utils.generate_glance_url()
        http_url = "http://%s:%d" % (CONF.glance.glance_host,
                                     CONF.glance.glance_port)
        self.assertEqual(http_url, generated_url)

    def test_generate_glance_https_url(self):
        self.config(glance_protocol="https", group='glance')
        self.config(glance_host="127.0.0.1", group='glance')
        generated_url = service_utils.generate_glance_url()
        https_url = "https://%s:%d" % (CONF.glance.glance_host,
                                       CONF.glance.glance_port)
        self.assertEqual(https_url, generated_url)


class TestServiceUtils(base.TestCase):

    def test_parse_image_ref_no_ssl(self):
        image_href = u'http://127.0.0.1:9292/image_path/'\
            u'image_\u00F9\u00FA\u00EE\u0111'
        parsed_href = service_utils.parse_image_ref(image_href)
        self.assertEqual((u'image_\u00F9\u00FA\u00EE\u0111',
                          '127.0.0.1', 9292, False), parsed_href)

    def test_parse_image_ref_ssl(self):
        image_href = 'https://127.0.0.1:9292/image_path/'\
                     u'image_\u00F9\u00FA\u00EE\u0111'
        parsed_href = service_utils.parse_image_ref(image_href)
        self.assertEqual((u'image_\u00F9\u00FA\u00EE\u0111',
                          '127.0.0.1', 9292, True), parsed_href)

    def test_generate_image_url(self):
        image_href = u'image_\u00F9\u00FA\u00EE\u0111'
        self.config(glance_host='123.123.123.123', group='glance')
        self.config(glance_port=1234, group='glance')
        self.config(glance_protocol='https', group='glance')
        generated_url = service_utils.generate_image_url(image_href)
        self.assertEqual('https://123.123.123.123:1234/images/'
                         u'image_\u00F9\u00FA\u00EE\u0111',
                         generated_url)

    def test_is_glance_image(self):
        image_href = u'uui\u0111'
        self.assertFalse(service_utils.is_glance_image(image_href))
        image_href = u'733d1c44-a2ea-414b-aca7-69decf20d810'
        self.assertTrue(service_utils.is_glance_image(image_href))
        image_href = u'glance://uui\u0111'
        self.assertTrue(service_utils.is_glance_image(image_href))
        image_href = 'http://aaa/bbb'
        self.assertFalse(service_utils.is_glance_image(image_href))
        image_href = None
        self.assertFalse(service_utils.is_glance_image(image_href))

    def test_is_image_href_ordinary_file_name_true(self):
        image = u"\u0111eploy.iso"
        result = service_utils.is_image_href_ordinary_file_name(image)
        self.assertTrue(result)

    def test_is_image_href_ordinary_file_name_false(self):
        for image in ('733d1c44-a2ea-414b-aca7-69decf20d810',
                      u'glance://\u0111eploy_iso',
                      u'http://\u0111eploy_iso',
                      u'https://\u0111eploy_iso',
                      u'file://\u0111eploy_iso',):
            result = service_utils.is_image_href_ordinary_file_name(image)
            self.assertFalse(result)


class TestGlanceAPIServers(base.TestCase):

    def setUp(self):
        super(TestGlanceAPIServers, self).setUp()
        service_utils._GLANCE_API_SERVER = None

    def test__get_api_servers_default(self):
        host, port, use_ssl = service_utils._get_api_server()
        self.assertEqual(CONF.glance.glance_host, host)
        self.assertEqual(CONF.glance.glance_port, port)
        self.assertEqual(CONF.glance.glance_protocol == 'https', use_ssl)

    def test__get_api_servers_one(self):
        CONF.set_override('glance_api_servers', ['https://10.0.0.1:9293'],
                          'glance')
        s1 = service_utils._get_api_server()
        s2 = service_utils._get_api_server()
        self.assertEqual(('10.0.0.1', 9293, True), s1)

        # Only one server, should always get the same one
        self.assertEqual(s1, s2)

    def test__get_api_servers_two(self):
        CONF.set_override('glance_api_servers',
                          ['http://10.0.0.1:9293', 'http://10.0.0.2:9294'],
                          'glance')
        s1 = service_utils._get_api_server()
        s2 = service_utils._get_api_server()
        s3 = service_utils._get_api_server()

        self.assertNotEqual(s1, s2)

        # 2 servers, so cycles to the first again
        self.assertEqual(s1, s3)
