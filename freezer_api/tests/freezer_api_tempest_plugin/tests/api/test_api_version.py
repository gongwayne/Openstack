# (C) Copyright 2016 Hewlett Packard Enterprise Development Company LP
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

from freezer_api.tests.freezer_api_tempest_plugin.tests.api import base
from tempest import test

class TestFreezerApiVersion(base.BaseFreezerApiTest):

    @classmethod
    def resource_setup(cls):
        super(TestFreezerApiVersion, cls).resource_setup()

    @classmethod
    def resource_cleanup(cls):
        super(TestFreezerApiVersion, cls).resource_cleanup()

    @test.attr(type="gate")
    def test_api_version(self):

        resp, response_body = self.freezer_api_client.get_version()
        self.assertEqual(300, resp.status)
