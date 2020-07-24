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

import abc

import six
from trove.common.strategies.strategy import Strategy


@six.add_metaclass(abc.ABCMeta)
class Replication(Strategy):
    """Base class for Replication Strategy implementation."""

    __strategy_type__ = 'replication'
    __strategy_ns__ = 'trove.guestagent.strategies.replication'

    def __init__(self):
        super(Replication, self).__init__()

    @abc.abstractmethod
    def get_main_ref(self, service, snapshot_info):
        """Get reference to main site for replication strategy."""

    def backup_required_for_replication(self):
        """Indicates whether a backup is required for replication."""
        return True

    @abc.abstractmethod
    def snapshot_for_replication(self, context, service, location,
                                 snapshot_info):
        """Capture snapshot of main db."""

    @abc.abstractmethod
    def enable_as_main(self, service, main_config):
        """Configure underlying database to act as main for replication."""

    @abc.abstractmethod
    def enable_as_subordinate(self, service, snapshot, subordinate_config):
        """Configure underlying database as a subordinate of the given main."""

    @abc.abstractmethod
    def detach_subordinate(self, service, for_failover):
        """Turn off replication on a subordinate site."""

    @abc.abstractmethod
    def cleanup_source_on_replica_detach(self, service, replica_info):
        """Clean up the source on the detach of a replica."""

    @abc.abstractmethod
    def demote_main(self, service):
        """Turn off replication on a main site."""
