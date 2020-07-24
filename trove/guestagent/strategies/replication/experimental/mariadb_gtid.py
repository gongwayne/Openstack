# Copyright 2016 Tesora, Inc.
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
#

from oslo_log import log as logging

from trove.common import cfg
from trove.guestagent.backup.backupagent import BackupAgent
from trove.guestagent.strategies.replication import mysql_base

AGENT = BackupAgent()
CONF = cfg.CONF

LOG = logging.getLogger(__name__)


class MariaDBGTIDReplication(mysql_base.MysqlReplicationBase):
    """MariaDB Replication coordinated by GTIDs."""

    def connect_to_main(self, service, snapshot):
        logging_config = snapshot['log_position']
        LOG.debug("connect_to_main %s" % logging_config['replication_user'])
        change_main_cmd = (
            "CHANGE MASTER TO MASTER_HOST='%(host)s', "
            "MASTER_PORT=%(port)s, "
            "MASTER_USER='%(user)s', "
            "MASTER_PASSWORD='%(password)s', "
            "MASTER_USE_GTID=subordinate_pos" %
            {
                'host': snapshot['main']['host'],
                'port': snapshot['main']['port'],
                'user': logging_config['replication_user']['name'],
                'password': logging_config['replication_user']['password']
            })
        service.execute_on_client(change_main_cmd)
        service.start_subordinate()
