# -*- encoding: utf-8 -*-
#
# Copyright 2013 - Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import uuid

import mock
from oslo_config import cfg
import six
import wsme

from solum.common import exception
from solum.tests import base


class ExceptionTestCase(base.BaseTestCase):
    """Test cases for exception code."""

    def test_with_kwargs(self):
        exc = exception.ResourceNotFound(name='application', id='green_paint')
        self.assertIn('green_paint could not be found.',
                      six.text_type(exc))
        self.assertEqual(exc.code, 404)

    def test_with_kwargs_ru(self):
        exc = exception.ResourceNotFound(name='application',
                                         id=u'зеленой_краской')
        self.assertIn(u'зеленой_краской could not be found',
                      six.text_type(exc))
        self.assertEqual(exc.code, 404)

    def test_bad_kwargs_exception(self):
        cfg.CONF.set_override('fatal_exception_format_errors', True)
        self.assertRaises(KeyError,
                          exception.ResourceNotFound, a_field='green')

    def test_bad_kwargs(self):
        cfg.CONF.set_override('fatal_exception_format_errors', False)
        exc = exception.ResourceNotFound(a_field='green')
        self.assertIn('An unknown exception occurred', six.text_type(exc))
        self.assertEqual(exc.code, 404)

    def test_resource_exists(self):
        exc = exception.ResourceExists(name='test')
        self.assertIn("The test resource already exists.",
                      six.text_type(exc))
        self.assertEqual(exc.code, 409)

    def test_application_exists(self):
        exc = exception.ResourceExists(name='test')
        self.assertIn("The test resource already exists.",
                      six.text_type(exc))
        self.assertEqual(exc.code, 409)

    def test_not_implemented(self):
        exc = exception.NotImplemented()
        self.assertIn("The requested operation is not implemented.",
                      six.text_type(exc))
        self.assertEqual(exc.code, 501)

    def test_wrap_controller_exception_with_server_error(self):
        exception.LOG.error = mock.Mock()

        def error_func():
            raise exception.NotImplemented()

        correlation_id = None
        try:
            exception.wrap_wsme_controller_exception(error_func)()
        except wsme.exc.ClientSideError as e:
            correlation_id = six.text_type(e).split(":")[1].strip()

        self.assertIsNotNone(correlation_id)
        self.assertIsInstance(uuid.UUID(correlation_id), uuid.UUID)
        self.assertTrue(exception.LOG.error.called)

        (args, kargs) = exception.LOG.error.call_args

        self.assertTrue(correlation_id in args)
        self.assertTrue(correlation_id in str(args[0] % args[1:]))

    def test_wrap_controller_exception_with_client_error(self):
        error_args = dict(reason="foo")
        expected_error_msg = six.text_type(
            exception.BadRequest.msg_fmt % error_args)

        def error_func():
            raise exception.BadRequest(**error_args)

        try:
            exception.wrap_wsme_controller_exception(error_func)()
            self.assertTrue(False)
        except wsme.exc.ClientSideError as e:
            self.assertEqual(e.msg, expected_error_msg)

    def test_wrap_controller_exception_with_uncatched_error(self):
        exception.LOG.error = mock.Mock()

        def error_func():
            value_error = ValueError('Hey!')
            value_error.code = 500
            raise value_error

        correlation_id = None
        try:
            exception.wrap_wsme_controller_exception(error_func)()
        except wsme.exc.ClientSideError as e:
            correlation_id = six.text_type(e).split(":")[1].strip()

        self.assertIsNotNone(correlation_id)
        self.assertIsInstance(uuid.UUID(correlation_id), uuid.UUID)
        self.assertTrue(exception.LOG.error.called)

        (args, kargs) = exception.LOG.error.call_args

        self.assertTrue(correlation_id in args)
        self.assertTrue(correlation_id in str(args[0] % args[1:]))
