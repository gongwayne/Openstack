# Copyright 2014 Tesora, Inc.
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
from oslo_utils import netutils

from trove.common import cfg
from trove.guestagent.strategies.replication import base

CONF = cfg.CONF

LOG = logging.getLogger(__name__)


class RedisSyncReplication(base.Replication):
    """Redis Replication strategy."""

    __strategy_ns__ = 'trove.guestagent.strategies.replication.experimental'
    __strategy_name__ = 'RedisSyncReplication'

    CONF_LABEL_REPLICATION_MASTER = 'replication_main'
    CONF_LABEL_REPLICATION_SLAVE = 'replication_subordinate'

    def get_main_ref(self, service, snapshot_info):
        main_ref = {
            'host': netutils.get_my_ipv4(),
            'port': service.get_port(),
            'requirepass': service.get_auth_password(),
        }
        return main_ref

    def backup_required_for_replication(self):
        LOG.debug('Request for replication backup: no backup required')
        return False

    def snapshot_for_replication(self, context, service,
                                 location, snapshot_info):
        return None, None

    def enable_as_main(self, service, main_config):
        service.configuration_manager.apply_system_override(
            main_config, change_id=self.CONF_LABEL_REPLICATION_MASTER)
        service.restart()

    def enable_as_subordinate(self, service, snapshot, subordinate_config):
        service.configuration_manager.apply_system_override(
            subordinate_config, change_id=self.CONF_LABEL_REPLICATION_SLAVE)
        main_info = snapshot['main']
        main_host = main_info['host']
        main_port = main_info['port']
        connect_options = {'subordinateof': [main_host, main_port]}
        main_passwd = main_info.get('requirepass')
        if main_passwd:
            connect_options['mainauth'] = main_passwd
            service.admin.config_set('mainauth', main_passwd)
        else:
            service.admin.config_set('mainauth', "")
        service.configuration_manager.apply_system_override(
            connect_options, change_id=self.CONF_LABEL_REPLICATION_SLAVE)
        service.admin.set_main(host=main_host, port=main_port)
        LOG.debug('Enabled as subordinate.')

    def detach_subordinate(self, service, for_failover):
        service.configuration_manager.remove_system_override(
            change_id=self.CONF_LABEL_REPLICATION_SLAVE)
        service.admin.set_main(host=None, port=None)
        service.admin.config_set('mainauth', "")
        return None

    def cleanup_source_on_replica_detach(self, service, replica_info):
        # Nothing needs to be done to the main when a replica goes away.
        pass

    def get_replica_context(self, service):
        return {
            'main': self.get_main_ref(service, None),
        }

    def demote_main(self, service):
        service.configuration_manager.remove_system_override(
            change_id=self.CONF_LABEL_REPLICATION_MASTER)
