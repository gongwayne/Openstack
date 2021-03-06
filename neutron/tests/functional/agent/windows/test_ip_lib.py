# Copyright 2016 Cloudbase Solutions.
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

from neutron.agent.windows import ip_lib
from neutron.tests import base

WRONG_IP = '0.0.0.0'
TEST_IP = '127.0.0.1'


class IpLibTestCase(base.BaseTestCase):

    def test_ipwrapper_get_device_by_ip_None(self):
        self.assertIsNone(ip_lib.IPWrapper().get_device_by_ip(WRONG_IP))

    def test_ipwrapper_get_device_by_ip(self):
        ip_dev = ip_lib.IPWrapper().get_device_by_ip(TEST_IP)
        self.assertEqual('lo', ip_dev.device_name)

    def test_device_has_ip(self):
        not_a_device = ip_lib.IPDevice('#!#._not_a_device_bleargh!!@@@')
        self.assertFalse(not_a_device.device_has_ip(TEST_IP))
