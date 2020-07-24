# Copyright 2014 Hewlett-Packard Development Company, L.P.
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
from time import sleep

from proboscis.asserts import assert_equal
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis.decorators import time_out
from proboscis import SkipTest
from proboscis import test
from troveclient.compat import exceptions

from trove.common.utils import generate_uuid
from trove.common.utils import poll_until
from trove.tests.api.instances import CheckInstance
from trove.tests.api.instances import instance_info
from trove.tests.api.instances import TIMEOUT_INSTANCE_CREATE
from trove.tests.api.instances import TIMEOUT_INSTANCE_DELETE
from trove.tests.api.instances import WaitForGuestInstallationToFinish
from trove.tests.config import CONFIG
from trove.tests.util.server_connection import create_server_connection


class SubordinateInstanceTestInfo(object):
    """Stores subordinate instance information."""
    def __init__(self):
        self.id = None
        self.replicated_db = generate_uuid()


GROUP = "dbaas.api.replication"
subordinate_instance = SubordinateInstanceTestInfo()
existing_db_on_main = generate_uuid()
backup_count = None


def _get_user_count(server_info):
    cmd = ('mysql -BNq -e \\\'select count\\(*\\) from mysql.user'
           ' where user like \\\"subordinate_%\\\"\\\'')
    server = create_server_connection(server_info.id)
    stdout, stderr = server.execute(cmd)
    return int(stdout.rstrip())


def subordinate_is_running(running=True):

    def check_subordinate_is_running():
        server = create_server_connection(subordinate_instance.id)
        cmd = ("mysqladmin extended-status "
               "| awk '/Subordinate_running/{print $4}'")
        stdout, stderr = server.execute(cmd)
        expected = "ON" if running else "OFF"
        return stdout.rstrip() == expected

    return check_subordinate_is_running


def backup_count_matches(count):

    def check_backup_count_matches():
        backup = instance_info.dbaas.instances.backups(instance_info.id)
        return count == len(backup)

    return check_backup_count_matches


def instance_is_active(id):
    instance = instance_info.dbaas.instances.get(id)
    if instance.status == "ACTIVE":
        return True
    else:
        assert_true(instance.status in ['PROMOTE', 'EJECT', 'BUILD', 'BACKUP'])
        return False


def create_subordinate():
    result = instance_info.dbaas.instances.create(
        instance_info.name + "_subordinate",
        instance_info.dbaas_flavor_href,
        instance_info.volume,
        nics=instance_info.nics,
        datastore=instance_info.dbaas_datastore,
        datastore_version=instance_info.dbaas_datastore_version,
        subordinate_of=instance_info.id)
    assert_equal(200, instance_info.dbaas.last_http_code)
    assert_equal("BUILD", result.status)
    return result.id


def validate_subordinate(main, subordinate):
    new_subordinate = instance_info.dbaas.instances.get(subordinate.id)
    assert_equal(200, instance_info.dbaas.last_http_code)
    ns_dict = new_subordinate._info
    CheckInstance(ns_dict).subordinate_of()
    assert_equal(main.id, ns_dict['replica_of']['id'])


def validate_main(main, subordinates):
    new_main = instance_info.dbaas.instances.get(main.id)
    assert_equal(200, instance_info.dbaas.last_http_code)
    nm_dict = new_main._info
    CheckInstance(nm_dict).subordinates()
    main_ids = set([replica['id'] for replica in nm_dict['replicas']])
    asserted_ids = set([subordinate.id for subordinate in subordinates])
    assert_true(asserted_ids.issubset(main_ids))


@test(depends_on_classes=[WaitForGuestInstallationToFinish],
      groups=[GROUP])
class CreateReplicationSubordinate(object):

    @test
    def test_replica_provisioning_with_missing_replica_source(self):
        assert_raises(exceptions.NotFound,
                      instance_info.dbaas.instances.create,
                      instance_info.name + "_subordinate",
                      instance_info.dbaas_flavor_href,
                      instance_info.volume,
                      datastore=instance_info.dbaas_datastore,
                      datastore_version=instance_info.dbaas_datastore_version,
                      subordinate_of="Missing replica source")
        assert_equal(404, instance_info.dbaas.last_http_code)

    @test
    def test_create_db_on_main(self):
        databases = [{'name': existing_db_on_main}]
        # Ensure that the auth_token in the dbaas client is not stale
        instance_info.dbaas.authenticate()
        instance_info.dbaas.databases.create(instance_info.id, databases)
        assert_equal(202, instance_info.dbaas.last_http_code)

    @test(runs_after=['test_create_db_on_main'])
    def test_create_subordinate(self):
        global backup_count
        backup_count = len(
            instance_info.dbaas.instances.backups(instance_info.id))
        subordinate_instance.id = create_subordinate()


@test(groups=[GROUP])
class WaitForCreateSubordinateToFinish(object):
    """Wait until the instance is created and set up as subordinate."""

    @test(depends_on=[CreateReplicationSubordinate.test_create_subordinate])
    @time_out(TIMEOUT_INSTANCE_CREATE)
    def test_subordinate_created(self):
        poll_until(lambda: instance_is_active(subordinate_instance.id))


@test(enabled=(not CONFIG.fake_mode),
      depends_on=[WaitForCreateSubordinateToFinish],
      groups=[GROUP])
class VerifySubordinate(object):

    def db_is_found(self, database_to_find):

        def find_database():
            databases = instance_info.dbaas.databases.list(subordinate_instance.id)
            return (database_to_find
                    in [d.name for d in databases])

        return find_database

    @test
    @time_out(5 * 60)
    def test_correctly_started_replication(self):
        poll_until(subordinate_is_running())

    @test(runs_after=[test_correctly_started_replication])
    @time_out(60)
    def test_backup_deleted(self):
        poll_until(backup_count_matches(backup_count))

    @test(depends_on=[test_correctly_started_replication])
    def test_subordinate_is_read_only(self):
        cmd = "mysql -BNq -e \\\'select @@read_only\\\'"
        server = create_server_connection(subordinate_instance.id)
        stdout, stderr = server.execute(cmd)
        assert_equal(stdout, "1\n")

    @test(depends_on=[test_subordinate_is_read_only])
    def test_create_db_on_main(self):
        databases = [{'name': subordinate_instance.replicated_db}]
        instance_info.dbaas.databases.create(instance_info.id, databases)
        assert_equal(202, instance_info.dbaas.last_http_code)

    @test(depends_on=[test_create_db_on_main])
    @time_out(5 * 60)
    def test_database_replicated_on_subordinate(self):
        poll_until(self.db_is_found(subordinate_instance.replicated_db))

    @test(runs_after=[test_database_replicated_on_subordinate])
    @time_out(5 * 60)
    def test_existing_db_exists_on_subordinate(self):
        poll_until(self.db_is_found(existing_db_on_main))

    @test(depends_on=[test_existing_db_exists_on_subordinate])
    def test_subordinate_user_exists(self):
        assert_equal(_get_user_count(subordinate_instance), 1)
        assert_equal(_get_user_count(instance_info), 1)


@test(groups=[GROUP],
      depends_on=[WaitForCreateSubordinateToFinish],
      runs_after=[VerifySubordinate])
class TestInstanceListing(object):
    """Test replication information in instance listing."""

    @test
    def test_get_subordinate_instance(self):
        validate_subordinate(instance_info, subordinate_instance)

    @test
    def test_get_main_instance(self):
        validate_main(instance_info, [subordinate_instance])


@test(groups=[GROUP],
      depends_on=[WaitForCreateSubordinateToFinish],
      runs_after=[TestInstanceListing])
class TestReplicationFailover(object):
    """Test replication failover functionality."""

    @staticmethod
    def promote(main, subordinate):
        if CONFIG.fake_mode:
            raise SkipTest("promote_replica_source not supported in fake mode")

        instance_info.dbaas.instances.promote_to_replica_source(subordinate)
        assert_equal(202, instance_info.dbaas.last_http_code)
        poll_until(lambda: instance_is_active(subordinate.id))
        validate_main(subordinate, [main])
        validate_subordinate(subordinate, main)

    @test
    def test_promote_main(self):
        if CONFIG.fake_mode:
            raise SkipTest("promote_main not supported in fake mode")

        assert_raises(exceptions.BadRequest,
                      instance_info.dbaas.instances.promote_to_replica_source,
                      instance_info.id)

    @test
    def test_eject_subordinate(self):
        if CONFIG.fake_mode:
            raise SkipTest("eject_replica_source not supported in fake mode")

        assert_raises(exceptions.BadRequest,
                      instance_info.dbaas.instances.eject_replica_source,
                      subordinate_instance.id)

    @test
    def test_eject_valid_main(self):
        if CONFIG.fake_mode:
            raise SkipTest("eject_replica_source not supported in fake mode")

        assert_raises(exceptions.BadRequest,
                      instance_info.dbaas.instances.eject_replica_source,
                      instance_info.id)

    @test(depends_on=[test_promote_main, test_eject_subordinate,
                      test_eject_valid_main])
    def test_promote_to_replica_source(self):
        TestReplicationFailover.promote(instance_info, subordinate_instance)

    @test(depends_on=[test_promote_to_replica_source])
    def test_promote_back_to_replica_source(self):
        TestReplicationFailover.promote(subordinate_instance, instance_info)

    @test(depends_on=[test_promote_back_to_replica_source], enabled=False)
    def add_second_subordinate(self):
        if CONFIG.fake_mode:
            raise SkipTest("three site promote not supported in fake mode")

        self._third_subordinate = SubordinateInstanceTestInfo()
        self._third_subordinate.id = create_subordinate()
        poll_until(lambda: instance_is_active(self._third_subordinate.id))
        poll_until(subordinate_is_running())
        sleep(30)
        validate_main(instance_info, [subordinate_instance, self._third_subordinate])
        validate_subordinate(instance_info, self._third_subordinate)

    @test(depends_on=[add_second_subordinate], enabled=False)
    def test_three_site_promote(self):
        if CONFIG.fake_mode:
            raise SkipTest("three site promote not supported in fake mode")

        TestReplicationFailover.promote(instance_info, self._third_subordinate)
        validate_main(self._third_subordinate, [subordinate_instance, instance_info])
        validate_subordinate(self._third_subordinate, instance_info)

    @test(depends_on=[test_three_site_promote], enabled=False)
    def disable_main(self):
        if CONFIG.fake_mode:
            raise SkipTest("eject_replica_source not supported in fake mode")

        cmd = "sudo service trove-guestagent stop"
        server = create_server_connection(self._third_subordinate.id)
        stdout, stderr = server.execute(cmd)
        assert_equal(stdout, "1\n")

    @test(depends_on=[disable_main], enabled=False)
    def test_eject_replica_main(self):
        if CONFIG.fake_mode:
            raise SkipTest("eject_replica_source not supported in fake mode")

        sleep(90)
        instance_info.dbaas.instances.eject_replica_source(self._third_subordinate)
        assert_equal(202, instance_info.dbaas.last_http_code)
        poll_until(lambda: instance_is_active(self._third_subordinate.id))
        validate_main(instance_info, [subordinate_instance])
        validate_subordinate(instance_info, subordinate_instance)


@test(groups=[GROUP],
      depends_on=[WaitForCreateSubordinateToFinish],
      runs_after=[TestReplicationFailover])
class DetachReplica(object):

    @test
    def delete_before_detach_replica(self):
        assert_raises(exceptions.Forbidden,
                      instance_info.dbaas.instances.delete,
                      instance_info.id)

    @test
    @time_out(5 * 60)
    def test_detach_replica(self):
        if CONFIG.fake_mode:
            raise SkipTest("Detach replica not supported in fake mode")

        instance_info.dbaas.instances.edit(subordinate_instance.id,
                                           detach_replica_source=True)
        assert_equal(202, instance_info.dbaas.last_http_code)

        poll_until(subordinate_is_running(False))

    @test(depends_on=[test_detach_replica])
    @time_out(5 * 60)
    def test_subordinate_is_not_read_only(self):
        if CONFIG.fake_mode:
            raise SkipTest("Test not_read_only not supported in fake mode")

        # wait until replica is no longer read only
        def check_not_read_only():
            cmd = "mysql -BNq -e \\\'select @@read_only\\\'"
            server = create_server_connection(subordinate_instance.id)
            stdout, stderr = server.execute(cmd)
            if (stdout.rstrip() != "0"):
                return False
            else:
                return True
        poll_until(check_not_read_only)


@test(groups=[GROUP],
      depends_on=[WaitForCreateSubordinateToFinish],
      runs_after=[DetachReplica])
class DeleteSubordinateInstance(object):

    @test
    @time_out(TIMEOUT_INSTANCE_DELETE)
    def test_delete_subordinate_instance(self):
        instance_info.dbaas.instances.delete(subordinate_instance.id)
        assert_equal(202, instance_info.dbaas.last_http_code)

        def instance_is_gone():
            try:
                instance_info.dbaas.instances.get(subordinate_instance.id)
                return False
            except exceptions.NotFound:
                return True

        poll_until(instance_is_gone)
        assert_raises(exceptions.NotFound, instance_info.dbaas.instances.get,
                      subordinate_instance.id)
