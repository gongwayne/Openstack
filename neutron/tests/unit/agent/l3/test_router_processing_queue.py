# Copyright 2014 Hewlett-Packard Development Company, L.P.
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
#

import datetime

from oslo_utils import uuidutils

from neutron.agent.l3 import router_processing_queue as l3_queue
from neutron.tests import base

_uuid = uuidutils.generate_uuid
FAKE_ID = _uuid()
FAKE_ID_2 = _uuid()


class TestExclusiveRouterProcessor(base.BaseTestCase):
    def setUp(self):
        super(TestExclusiveRouterProcessor, self).setUp()

    def test_i_am_main(self):
        main = l3_queue.ExclusiveRouterProcessor(FAKE_ID)
        not_main = l3_queue.ExclusiveRouterProcessor(FAKE_ID)
        main_2 = l3_queue.ExclusiveRouterProcessor(FAKE_ID_2)
        not_main_2 = l3_queue.ExclusiveRouterProcessor(FAKE_ID_2)

        self.assertTrue(main._i_am_main())
        self.assertFalse(not_main._i_am_main())
        self.assertTrue(main_2._i_am_main())
        self.assertFalse(not_main_2._i_am_main())

        main.__exit__(None, None, None)
        main_2.__exit__(None, None, None)

    def test_main(self):
        main = l3_queue.ExclusiveRouterProcessor(FAKE_ID)
        not_main = l3_queue.ExclusiveRouterProcessor(FAKE_ID)
        main_2 = l3_queue.ExclusiveRouterProcessor(FAKE_ID_2)
        not_main_2 = l3_queue.ExclusiveRouterProcessor(FAKE_ID_2)

        self.assertEqual(main, main._main)
        self.assertEqual(main, not_main._main)
        self.assertEqual(main_2, main_2._main)
        self.assertEqual(main_2, not_main_2._main)

        main.__exit__(None, None, None)
        main_2.__exit__(None, None, None)

    def test__enter__(self):
        self.assertNotIn(FAKE_ID, l3_queue.ExclusiveRouterProcessor._mains)
        main = l3_queue.ExclusiveRouterProcessor(FAKE_ID)
        main.__enter__()
        self.assertIn(FAKE_ID, l3_queue.ExclusiveRouterProcessor._mains)
        main.__exit__(None, None, None)

    def test__exit__(self):
        main = l3_queue.ExclusiveRouterProcessor(FAKE_ID)
        not_main = l3_queue.ExclusiveRouterProcessor(FAKE_ID)
        main.__enter__()
        self.assertIn(FAKE_ID, l3_queue.ExclusiveRouterProcessor._mains)
        not_main.__enter__()
        not_main.__exit__(None, None, None)
        self.assertIn(FAKE_ID, l3_queue.ExclusiveRouterProcessor._mains)
        main.__exit__(None, None, None)
        self.assertNotIn(FAKE_ID, l3_queue.ExclusiveRouterProcessor._mains)

    def test_data_fetched_since(self):
        main = l3_queue.ExclusiveRouterProcessor(FAKE_ID)
        self.assertEqual(datetime.datetime.min,
                         main._get_router_data_timestamp())

        ts1 = datetime.datetime.utcnow() - datetime.timedelta(seconds=10)
        ts2 = datetime.datetime.utcnow()

        main.fetched_and_processed(ts2)
        self.assertEqual(ts2, main._get_router_data_timestamp())
        main.fetched_and_processed(ts1)
        self.assertEqual(ts2, main._get_router_data_timestamp())

        main.__exit__(None, None, None)

    def test_updates(self):
        main = l3_queue.ExclusiveRouterProcessor(FAKE_ID)
        not_main = l3_queue.ExclusiveRouterProcessor(FAKE_ID)

        main.queue_update(l3_queue.RouterUpdate(FAKE_ID, 0))
        not_main.queue_update(l3_queue.RouterUpdate(FAKE_ID, 0))

        for update in not_main.updates():
            raise Exception("Only the main should process a router")

        self.assertEqual(2, len([i for i in main.updates()]))
