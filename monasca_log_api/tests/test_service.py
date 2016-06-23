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

import datetime
import random
import string
import unittest

from falcon import errors
from falcon import testing
import mock

from monasca_log_api.api import exceptions
from monasca_log_api.api import logs_api
from monasca_log_api.reference.v2.common import service as common_service
from monasca_log_api.tests import base


class IsDelegate(unittest.TestCase):
    def test_is_delegate_ok_role(self):
        roles = logs_api.MONITORING_DELEGATE_ROLE
        self.assertTrue(common_service.is_delegate(roles))

    def test_is_delegate_ok_role_in_roles(self):
        roles = logs_api.MONITORING_DELEGATE_ROLE + ',a_role,b_role'
        self.assertTrue(common_service.is_delegate(roles))

    def test_is_delegate_not_ok_role(self):
        roles = 'a_role,b_role'
        self.assertFalse(common_service.is_delegate(roles))


class ParseDimensions(unittest.TestCase):
    def test_should_fail_for_empty_dimensions(self):
        self.assertRaises(exceptions.HTTPUnprocessableEntity,
                          common_service.parse_dimensions, '')
        self.assertRaises(exceptions.HTTPUnprocessableEntity,
                          common_service.parse_dimensions, None)

    def test_should_fail_for_empty_dim_in_dimensions(self):
        with self.assertRaises(exceptions.HTTPUnprocessableEntity) as context:
            common_service.parse_dimensions(',')

        self.assertEqual(context.exception.description,
                         'Dimension cannot be empty')

    def test_should_fail_for_invalid_dim_in_dimensions(self):
        invalid_dim = 'a'
        with self.assertRaises(exceptions.HTTPUnprocessableEntity) as context:
            common_service.parse_dimensions(invalid_dim)

        self.assertEqual(context.exception.description,
                         '%s is not a valid dimension' % invalid_dim)

    def test_should_pass_for_valid_dimensions(self):
        dimensions = 'a:1,b:2'
        expected = {
            'a': '1',
            'b': '2'
        }

        self.assertDictEqual(expected,
                             common_service.parse_dimensions(dimensions))


class ParseApplicationType(unittest.TestCase):
    def test_should_return_none_for_none(self):
        self.assertIsNone(common_service.parse_application_type(None))

    def test_should_return_none_for_empty(self):
        self.assertIsNone(common_service.parse_application_type(''))

    def test_should_return_none_for_whitespace_filled(self):
        self.assertIsNone(common_service.parse_application_type('    '))

    def test_should_return_value_for_ok_value(self):
        app_type = 'monasca'
        self.assertEqual(app_type,
                         common_service.parse_application_type(app_type))

    def test_should_return_value_for_ok_value_with_spaces(self):
        app_type = '  monasca  '
        expected = 'monasca'
        self.assertEqual(expected,
                         common_service.parse_application_type(app_type))


class ApplicationTypeValidations(unittest.TestCase):
    def test_should_pass_for_empty_app_type(self):
        common_service.Validations.validate_application_type()
        common_service.Validations.validate_application_type('')

    def test_should_fail_for_invalid_length(self):
        r_app_type = testing.rand_string(300, 600)
        with self.assertRaises(exceptions.HTTPUnprocessableEntity) as context:
            common_service.Validations.validate_application_type(r_app_type)

        length = common_service.APPLICATION_TYPE_CONSTRAINTS['MAX_LENGTH']
        msg = ('Application type {type} must be '
               '{length} characters or less'.format(type=r_app_type,
                                                    length=length))

        self.assertEqual(context.exception.description, msg)

    def test_should_fail_for_invalid_content(self):
        r_app_type = '%#$@!'
        with self.assertRaises(exceptions.HTTPUnprocessableEntity) as context:
            common_service.Validations.validate_application_type(r_app_type)

        msg = ('Application type %s may only contain: "a-z A-Z 0-9 _ - ."' %
               r_app_type)

        self.assertEqual(context.exception.description, msg)

    def test_should_pass_for_ok_app_type(self):
        r_app_type = 'monasca'
        common_service.Validations.validate_application_type(r_app_type)


class DimensionsValidations(unittest.TestCase):
    @unittest.expectedFailure
    def test_should_fail_for_none_dimensions(self):
        common_service.Validations.validate_dimensions(None)

    @unittest.expectedFailure
    def test_should_fail_pass_for_non_iterable_dimensions_str(self):
        common_service.Validations.validate_dimensions('')

    @unittest.expectedFailure
    def test_should_fail_pass_for_non_iterable_dimensions_number(self):
        common_service.Validations.validate_dimensions(1)

    def test_should_pass_for_empty_dimensions_array(self):
        common_service.Validations.validate_dimensions({})

    def test_should_fail_too_empty_name(self):
        dimensions = {'': 1}
        with self.assertRaises(exceptions.HTTPUnprocessableEntity) as context:
            common_service.Validations.validate_dimensions(dimensions)

        msg = 'Dimension name cannot be empty'
        self.assertEqual(context.exception.description, msg)

    def test_should_fail_too_long_name(self):
        name = testing.rand_string(256, 260)
        dimensions = {name: 1}
        with self.assertRaises(exceptions.HTTPUnprocessableEntity) as context:
            common_service.Validations.validate_dimensions(dimensions)

        msg = 'Dimension name %s must be 255 characters or less' % name
        self.assertEqual(context.exception.description, msg)

    def test_should_fail_underscore_at_begin(self):
        name = '_aDim'
        dimensions = {name: 1}
        with self.assertRaises(exceptions.HTTPUnprocessableEntity) as context:
            common_service.Validations.validate_dimensions(dimensions)

        msg = 'Dimension name %s cannot start with underscore (_)' % name
        self.assertEqual(context.exception.description, msg)

    def test_should_fail_invalid_chars(self):
        name = '<>'
        dimensions = {name: 1}
        with self.assertRaises(exceptions.HTTPUnprocessableEntity) as context:
            common_service.Validations.validate_dimensions(dimensions)

        invalid_chars = '> < = { } ( ) \' " , ; &'
        msg = 'Dimension name %s may not contain: %s' % (name, invalid_chars)
        self.assertEqual(context.exception.description, msg)

    def test_should_fail_ok_name_empty_value(self):
        name = 'monasca'
        dimensions = {name: ''}
        with self.assertRaises(exceptions.HTTPUnprocessableEntity) as context:
            common_service.Validations.validate_dimensions(dimensions)

        msg = 'Dimension value cannot be empty'
        self.assertEqual(context.exception.description, msg)

    def test_should_fail_ok_name_too_long_value(self):
        name = 'monasca'
        value = testing.rand_string(256, 300)
        dimensions = {name: value}
        with self.assertRaises(exceptions.HTTPUnprocessableEntity) as context:
            common_service.Validations.validate_dimensions(dimensions)

        msg = 'Dimension value %s must be 255 characters or less' % value
        self.assertEqual(context.exception.description, msg)

    def test_should_pass_ok_name_ok_value_empty_service(self):
        name = 'monasca'
        value = '1'
        dimensions = {name: value}
        common_service.Validations.validate_dimensions(dimensions)

    def test_should_pass_ok_name_ok_value_service_SERVICE_DIMENSIONS_as_name(
            self):
        name = 'some_name'
        value = '1'
        dimensions = {name: value}
        common_service.Validations.validate_dimensions(dimensions)


class ContentTypeValidations(unittest.TestCase):

    def test_should_pass_text_plain(self):
        content_type = 'text/plain'
        req = mock.Mock()
        req.content_type = content_type
        common_service.Validations.validate_content_type(req)

    def test_should_pass_application_json(self):
        content_type = 'application/json'
        req = mock.Mock()
        req.content_type = content_type
        common_service.Validations.validate_content_type(req)

    def test_should_fail_invalid_content_type(self):
        content_type = 'no/such/type'
        req = mock.Mock()
        req.content_type = content_type
        self.assertRaises(
            errors.HTTPUnsupportedMediaType,
            common_service.Validations.validate_content_type,
            req
        )

    def test_should_fail_missing_header(self):
        content_type = None
        req = mock.Mock()
        req.content_type = content_type
        self.assertRaises(
            errors.HTTPMissingHeader,
            common_service.Validations.validate_content_type,
            req
        )


class PayloadSizeValidations(testing.TestBase):

    def setUp(self):
        self.conf = base.mock_config(self)
        return super(PayloadSizeValidations, self).setUp()

    def test_should_fail_missing_header(self):
        content_length = None
        req = mock.Mock()
        req.content_length = content_length
        self.assertRaises(
            errors.HTTPLengthRequired,
            common_service.Validations.validate_payload_size,
            req
        )

    def test_should_pass_limit_not_exceeded(self):
        content_length = 120
        max_log_size = 240
        self.conf.config(max_log_size=max_log_size,
                         group='service')

        req = mock.Mock()
        req.content_length = content_length

        common_service.Validations.validate_payload_size(req)

    def test_should_fail_limit_exceeded(self):
        content_length = 120
        max_log_size = 60
        self.conf.config(max_log_size=max_log_size,
                         group='service')

        req = mock.Mock()
        req.content_length = content_length

        self.assertRaises(
            errors.HTTPRequestEntityTooLarge,
            common_service.Validations.validate_payload_size,
            req
        )

    def test_should_fail_limit_equal(self):
        content_length = 120
        max_log_size = 120
        self.conf.config(max_log_size=max_log_size,
                         group='service')

        req = mock.Mock()
        req.content_length = content_length

        self.assertRaises(
            errors.HTTPRequestEntityTooLarge,
            common_service.Validations.validate_payload_size,
            req
        )


class EnvelopeSizeValidations(testing.TestBase):

    @staticmethod
    def _rand_str(size):
        return ''.join((random.choice(string.letters) for _ in range(size)))

    def setUp(self):
        self.conf = base.mock_config(self)
        return super(EnvelopeSizeValidations, self).setUp()

    def test_should_pass_envelope_size_ok(self):
        envelope = self._rand_str(120)
        max_log_size = 240
        self.conf.config(max_log_size=max_log_size,
                         group='service')

        common_service.Validations.validate_envelope_size(envelope)

    def test_should_pass_envelope_size_exceeded(self):
        envelope = self._rand_str(360)
        max_log_size = 240
        self.conf.config(max_log_size=max_log_size,
                         group='service')

        self.assertRaises(
            errors.HTTPInternalServerError,
            common_service.Validations.validate_envelope_size,
            envelope
        )

    def test_should_pass_envelope_size_equal(self):
        envelope = self._rand_str(240)
        max_log_size = 240
        self.conf.config(max_log_size=max_log_size,
                         group='service')

        self.assertRaises(
            errors.HTTPInternalServerError,
            common_service.Validations.validate_envelope_size,
            envelope
        )


class LogMessageValidations(testing.TestBase):

    def test_should_pass_message_in_log_property(self):
        log_object = {
            'message': 'some messages',
            'application_type': 'monasca-log-api',
            'dimensions': {
                'hostname': 'devstack'
            }
        }
        common_service.Validations.validate_log_message(log_object)

    @unittest.expectedFailure
    def test_should_fail_pass_for_non_message_in_log_property(self):
        log_object = {
            'massage': 'some messages',
            'application_type': 'monasca-log-api',
            'dimensions': {
                'hostname': 'devstack'
            }
        }
        common_service.Validations.validate_log_message(log_object)


class LogsCreatorNewLog(unittest.TestCase):
    def setUp(self):
        self.instance = common_service.LogCreator()

    @mock.patch('io.IOBase')
    def test_should_create_log_from_json(self, payload):
        msg = u'Hello World'
        path = u'/var/log/messages'
        json_msg = u'{"path":"%s","message":"%s"}' % (path, msg)
        app_type = 'monasca'
        dimensions = 'cpu_time:30'
        payload.read.return_value = json_msg

        expected_log = {
            'message': msg,
            'application_type': app_type,
            'dimensions': {
                'cpu_time': '30'
            },
            'path': path
        }

        self.assertEqual(expected_log, self.instance.new_log(
            application_type=app_type,
            dimensions=dimensions,
            payload=payload
        ))

    @mock.patch('io.IOBase')
    def test_should_create_log_from_text(self, payload):
        msg = u'Hello World'
        app_type = 'monasca'
        dimension_name = 'cpu_time'
        dimension_value = 30
        dimensions = '%s:%s' % (dimension_name, str(dimension_value))
        payload.read.return_value = msg

        expected_log = {
            'message': msg,
            'application_type': app_type,
            'dimensions': {
                dimension_name: str(dimension_value)
            }
        }

        self.assertEqual(expected_log, self.instance.new_log(
            application_type=app_type,
            dimensions=dimensions,
            payload=payload,
            content_type='text/plain'
        ))


class LogCreatorNewEnvelope(unittest.TestCase):
    def setUp(self):
        self.instance = common_service.LogCreator()

    def test_should_create_envelope(self):
        msg = u'Hello World'
        path = u'/var/log/messages'
        app_type = 'monasca'
        dimension_name = 'cpu_time'
        dimension_value = 30
        expected_log = {
            'message': msg,
            'application_type': app_type,
            'dimensions': {
                dimension_name: str(dimension_value)
            },
            'path': path
        }
        tenant_id = 'a_tenant'
        none = None
        meta = {'tenantId': tenant_id, 'region': none}
        timestamp = (datetime.datetime.utcnow() -
                     datetime.datetime(1970, 1, 1)).total_seconds()
        expected_envelope = {
            'log': expected_log,
            'creation_time': timestamp,
            'meta': meta
        }

        with mock.patch.object(self.instance, '_create_meta_info',
                               return_value=meta):
            actual_envelope = self.instance.new_log_envelope(expected_log,
                                                             tenant_id)

            self.assertEqual(expected_envelope.get('log'),
                             actual_envelope.get('log'))
            self.assertEqual(expected_envelope.get('meta'),
                             actual_envelope.get('meta'))
            self.assertDictEqual(
                expected_envelope.get('log').get('dimensions'),
                actual_envelope.get('log').get('dimensions'))

    @unittest.expectedFailure
    def test_should_not_create_log_none(self):
        log_object = None
        tenant_id = 'a_tenant'

        self.instance.new_log_envelope(log_object, tenant_id)

    @unittest.expectedFailure
    def test_should_not_create_log_empty(self):
        log_object = {}
        tenant_id = 'a_tenant'

        self.instance.new_log_envelope(log_object, tenant_id)

    @unittest.expectedFailure
    def test_should_not_create_tenant_none(self):
        log_object = {
            'message': ''
        }
        tenant_id = None

        self.instance.new_log_envelope(log_object, tenant_id)

    @unittest.expectedFailure
    def test_should_not_create_tenant_empty(self):
        log_object = {
            'message': ''
        }
        tenant_id = ''

        self.instance.new_log_envelope(log_object, tenant_id)