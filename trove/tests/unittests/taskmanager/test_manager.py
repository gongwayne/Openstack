# Copyright 2014 eBay Software Foundation
# Copyright [2015] Hewlett-Packard Development Company, L.P.
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

from mock import Mock, patch, PropertyMock

from trove.backup.models import Backup
from trove.instance.tasks import InstanceTasks
from trove.taskmanager.manager import Manager
from trove.taskmanager import models
from trove.taskmanager import service
from trove.common.exception import TroveError, ReplicationSubordinateAttachError
from proboscis.asserts import assert_equal
from trove.tests.unittests import trove_testtools


class TestManager(trove_testtools.TestCase):

    def setUp(self):
        super(TestManager, self).setUp()
        self.manager = Manager()
        self.context = trove_testtools.TroveTestContext(self)
        self.mock_subordinate1 = Mock()
        self.mock_subordinate2 = Mock()
        type(self.mock_subordinate1).id = PropertyMock(return_value='some-inst-id')
        type(self.mock_subordinate2).id = PropertyMock(return_value='inst1')

        self.mock_old_main = Mock()
        type(self.mock_old_main).subordinates = PropertyMock(
            return_value=[self.mock_subordinate1, self.mock_subordinate2])
        self.mock_main = Mock()
        type(self.mock_main).subordinates = PropertyMock(
            return_value=[self.mock_subordinate1, self.mock_subordinate2])

    def tearDown(self):
        super(TestManager, self).tearDown()
        self.manager = None

    def test_getattr_lookup(self):
        self.assertTrue(callable(self.manager.delete_cluster))
        self.assertTrue(callable(self.manager.mongodb_add_shard_cluster))

    def test_most_current_replica(self):
        main = Mock()
        main.id = 32

        def test_case(txn_list, selected_main):
            with patch.object(self.manager, '_get_replica_txns',
                              return_value=txn_list):
                result = self.manager._most_current_replica(main, None)
                assert_equal(result, selected_main)

        with self.assertRaisesRegexp(TroveError,
                                     'not all replicating from same'):
            test_case([['a', '2a99e-32bf', 2], ['b', '2a', 1]], None)

        test_case([['a', '2a99e-32bf', 2]], 'a')
        test_case([['a', '2a', 1], ['b', '2a', 2]], 'b')
        test_case([['a', '2a', 2], ['b', '2a', 1]], 'a')
        test_case([['a', '2a', 1], ['b', '2a', 1]], 'a')
        test_case([['a', None, 0]], 'a')
        test_case([['a', None, 0], ['b', '2a', 1]], 'b')

    def test_detach_replica(self):
        subordinate = Mock()
        main = Mock()
        with patch.object(models.BuiltInstanceTasks, 'load',
                          side_effect=[subordinate, main]):
            self.manager.detach_replica(self.context, 'some-inst-id')
        subordinate.detach_replica.assert_called_with(main)

    @patch.object(Manager, '_set_task_status')
    def test_promote_to_replica_source(self, mock_set_task_status):
        with patch.object(models.BuiltInstanceTasks, 'load',
                          side_effect=[self.mock_subordinate1,
                                       self.mock_old_main,
                                       self.mock_subordinate2]):
            self.manager.promote_to_replica_source(
                self.context, 'some-inst-id')

        self.mock_subordinate1.detach_replica.assert_called_with(
            self.mock_old_main, for_failover=True)
        self.mock_old_main.attach_replica.assert_called_with(
            self.mock_subordinate1)
        self.mock_subordinate1.make_read_only.assert_called_with(False)

        self.mock_subordinate2.detach_replica.assert_called_with(
            self.mock_old_main, for_failover=True)
        self.mock_subordinate2.attach_replica.assert_called_with(self.mock_subordinate1)

        self.mock_old_main.demote_replication_main.assert_any_call()

        mock_set_task_status.assert_called_with(([self.mock_old_main] +
                                                 [self.mock_subordinate1,
                                                  self.mock_subordinate2]),
                                                InstanceTasks.NONE)

    @patch.object(Manager, '_set_task_status')
    @patch.object(Manager, '_most_current_replica')
    def test_eject_replica_source(self, mock_most_current_replica,
                                  mock_set_task_status):
        with patch.object(models.BuiltInstanceTasks, 'load',
                          side_effect=[self.mock_main, self.mock_subordinate1,
                                       self.mock_subordinate2]):
            self.manager.eject_replica_source(self.context, 'some-inst-id')
        mock_most_current_replica.assert_called_with(self.mock_main,
                                                     [self.mock_subordinate1,
                                                      self.mock_subordinate2])
        mock_set_task_status.assert_called_with(([self.mock_main] +
                                                 [self.mock_subordinate1,
                                                  self.mock_subordinate2]),
                                                InstanceTasks.NONE)

    @patch.object(Manager, '_set_task_status')
    @patch('trove.taskmanager.manager.LOG')
    def test_exception_TroveError_promote_to_replica_source(self, *args):
        self.mock_subordinate2.detach_replica = Mock(side_effect=TroveError)
        with patch.object(models.BuiltInstanceTasks, 'load',
                          side_effect=[self.mock_subordinate1, self.mock_old_main,
                                       self.mock_subordinate2]):
            self.assertRaises(ReplicationSubordinateAttachError,
                              self.manager.promote_to_replica_source,
                              self.context, 'some-inst-id')

    @patch.object(Manager, '_set_task_status')
    @patch.object(Manager, '_most_current_replica')
    @patch('trove.taskmanager.manager.LOG')
    def test_exception_TroveError_eject_replica_source(
            self, mock_logging, mock_most_current_replica,
            mock_set_tast_status):
        self.mock_subordinate2.detach_replica = Mock(side_effect=TroveError)
        mock_most_current_replica.return_value = self.mock_subordinate1
        with patch.object(models.BuiltInstanceTasks, 'load',
                          side_effect=[self.mock_main, self.mock_subordinate1,
                                       self.mock_subordinate2]):
            self.assertRaises(ReplicationSubordinateAttachError,
                              self.manager.eject_replica_source,
                              self.context, 'some-inst-id')

    @patch.object(Manager, '_set_task_status')
    def test_error_promote_to_replica_source(self, *args):
        self.mock_subordinate2.detach_replica = Mock(
            side_effect=RuntimeError('Error'))

        with patch.object(models.BuiltInstanceTasks, 'load',
                          side_effect=[self.mock_subordinate1, self.mock_old_main,
                                       self.mock_subordinate2]):
            self.assertRaisesRegexp(RuntimeError, 'Error',
                                    self.manager.promote_to_replica_source,
                                    self.context, 'some-inst-id')

    @patch('trove.taskmanager.manager.LOG')
    def test_error_demote_replication_main_promote_to_replica_source(
            self, mock_logging):
        self.mock_old_main.demote_replication_main = Mock(
            side_effect=RuntimeError('Error'))

        with patch.object(models.BuiltInstanceTasks, 'load',
                          side_effect=[self.mock_subordinate1, self.mock_old_main,
                                       self.mock_subordinate2]):
            self.assertRaises(ReplicationSubordinateAttachError,
                              self.manager.promote_to_replica_source,
                              self.context, 'some-inst-id')

    @patch.object(Manager, '_set_task_status')
    @patch.object(Manager, '_most_current_replica')
    def test_error_eject_replica_source(self, mock_most_current_replica,
                                        mock_set_tast_status):
        self.mock_subordinate2.detach_replica = Mock(
            side_effect=RuntimeError('Error'))
        mock_most_current_replica.return_value = self.mock_subordinate1
        with patch.object(models.BuiltInstanceTasks, 'load',
                          side_effect=[self.mock_main, self.mock_subordinate1,
                                       self.mock_subordinate2]):
            self.assertRaisesRegexp(RuntimeError, 'Error',
                                    self.manager.eject_replica_source,
                                    self.context, 'some-inst-id')

    @patch.object(Backup, 'delete')
    def test_create_replication_subordinate(self, mock_backup_delete):
        mock_tasks = Mock()
        mock_snapshot = {'dataset': {'snapshot_id': 'test-id'}}
        mock_tasks.get_replication_main_snapshot = Mock(
            return_value=mock_snapshot)
        mock_flavor = Mock()
        with patch.object(models.FreshInstanceTasks, 'load',
                          return_value=mock_tasks):
            self.manager.create_instance(self.context, ['id1'], Mock(),
                                         mock_flavor, Mock(), None, None,
                                         'mysql', 'mysql-server', 2,
                                         'temp-backup-id', None,
                                         'some_password', None, Mock(),
                                         'some-main-id', None, None,
                                         None)
        mock_tasks.get_replication_main_snapshot.assert_called_with(
            self.context, 'some-main-id', mock_flavor, 'temp-backup-id',
            replica_number=1)
        mock_backup_delete.assert_called_with(self.context, 'test-id')

    @patch.object(models.FreshInstanceTasks, 'load')
    @patch.object(Backup, 'delete')
    @patch('trove.taskmanager.manager.LOG')
    def test_exception_create_replication_subordinate(self, mock_logging,
                                                mock_delete, mock_load):
        mock_load.return_value.create_instance = Mock(side_effect=TroveError)
        self.assertRaises(TroveError, self.manager.create_instance,
                          self.context, ['id1', 'id2'], Mock(), Mock(),
                          Mock(), None, None, 'mysql', 'mysql-server', 2,
                          'temp-backup-id', None, 'some_password', None,
                          Mock(), 'some-main-id', None, None, None)

    def test_AttributeError_create_instance(self):
        self.assertRaisesRegexp(
            AttributeError, 'Cannot create multiple non-replica instances.',
            self.manager.create_instance, self.context, ['id1', 'id2'],
            Mock(), Mock(), Mock(), None, None, 'mysql', 'mysql-server', 2,
            'temp-backup-id', None, 'some_password', None, Mock(), None, None,
            None, None)

    def test_create_instance(self):
        mock_tasks = Mock()
        mock_flavor = Mock()
        mock_override = Mock()
        with patch.object(models.FreshInstanceTasks, 'load',
                          return_value=mock_tasks):
            self.manager.create_instance(self.context, 'id1', 'inst1',
                                         mock_flavor, 'mysql-image-id', None,
                                         None, 'mysql', 'mysql-server', 2,
                                         'temp-backup-id', None, 'password',
                                         None, mock_override, None, None, None,
                                         None)
        mock_tasks.create_instance.assert_called_with(mock_flavor,
                                                      'mysql-image-id', None,
                                                      None, 'mysql',
                                                      'mysql-server', 2,
                                                      'temp-backup-id', None,
                                                      'password', None,
                                                      mock_override,
                                                      None, None, None, None)
        mock_tasks.wait_for_instance.assert_called_with(36000, mock_flavor)

    def test_create_cluster(self):
        mock_tasks = Mock()
        with patch.object(models, 'load_cluster_tasks',
                          return_value=mock_tasks):
            self.manager.create_cluster(self.context, 'some-cluster-id')
        mock_tasks.create_cluster.assert_called_with(self.context,
                                                     'some-cluster-id')

    def test_delete_cluster(self):
        mock_tasks = Mock()
        with patch.object(models, 'load_cluster_tasks',
                          return_value=mock_tasks):
            self.manager.delete_cluster(self.context, 'some-cluster-id')
        mock_tasks.delete_cluster.assert_called_with(self.context,
                                                     'some-cluster-id')


class TestTaskManagerService(trove_testtools.TestCase):
    def test_app_factory(self):
        test_service = service.app_factory(Mock())
        self.assertIsInstance(test_service, service.TaskService)
