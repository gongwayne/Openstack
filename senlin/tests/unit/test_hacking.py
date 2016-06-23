# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from senlin.hacking import checks
from senlin.tests.unit.common import base


class HackingTestCase(base.SenlinTestCase):
    def test_assert_equal_none(self):
        self.assertEqual(1, len(list(checks.assert_equal_none(
            "self.assertEqual(A, None)"))))

        self.assertEqual(1, len(list(checks.assert_equal_none(
            "self.assertEqual(None, A)"))))

        self.assertEqual(0, len(list(checks.assert_equal_none(
            "self.assertIsNone()"))))

    def test_use_jsonutils(self):
        def __get_msg(fun):
            msg = ("S319: jsonutils.%(fun)s must be used instead of "
                   "json.%(fun)s" % {'fun': fun})
            return [(0, msg)]

        for method in ('dump', 'dumps', 'load', 'loads'):
            self.assertEqual(__get_msg(method), list(checks.use_jsonutils(
                "json.%s(" % method, "./senlin/engine/cluster.py")))
            self.assertEqual(0, len(list(checks.use_jsonutils(
                "jsonx.%s(" % method, "./senlin/engine/cluster.py"))))
        self.assertEqual(0, len(list(checks.use_jsonutils(
            "json.dumb", "./senlin/engine/cluster.py"))))

    def test_no_mutable_default_args(self):
        self.assertEqual(1, len(list(checks.no_mutable_default_args(
            "def create_cluster(mapping={}, **params)"))))

        self.assertEqual(0, len(list(checks.no_mutable_default_args(
            "defined = []"))))

        self.assertEqual(0, len(list(checks.no_mutable_default_args(
            "defined, undefined = [], {}"))))
