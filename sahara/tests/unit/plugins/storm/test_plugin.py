# Copyright (c) 2015 TellesNobrega
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import mock

from sahara import conductor as cond
from sahara import context
from sahara.plugins import base as pb
from sahara.plugins import exceptions as ex
from sahara.plugins.storm import plugin as pl
from sahara.tests.unit import base


conductor = cond.API


class StormPluginTest(base.SaharaWithDbTestCase):
    def setUp(self):
        super(StormPluginTest, self).setUp()
        self.override_config("plugins", ["storm"])
        self.main_host = "main"
        self.main_inst = "6789"
        self.storm_topology_name = 'topology1'
        pb.setup_plugins()

    def _make_main_instance(self, return_code=0):
        main = mock.Mock()
        main.execute_command.return_value = (return_code,
                                               self.storm_topology_name)
        main.hostname.return_value = self.main_host
        main.id = self.main_inst
        return main

    def test_validate_existing_ng_scaling(self):
        data = {'name': "cluster",
                'plugin_name': "storm",
                'hadoop_version': "0.9.2",
                'node_groups': [
                    {'name': 'main',
                     'flavor_id': '42',
                     'count': 1,
                     'node_processes': ['nimbus']},
                    {'name': 'subordinate',
                     'flavor_id': '42',
                     'count': 1,
                     'node_processes': ['supervisor']},
                    {'name': 'zookeeper',
                     'flavor_id': '42',
                     'count': 1,
                     'node_processes': ['zookeeper']}
                    ]
                }
        cluster = conductor.cluster_create(context.ctx(), data)
        plugin = pb.PLUGINS.get_plugin(cluster.plugin_name)
        supervisor_id = [node.id for node in cluster.node_groups
                         if node.name == 'supervisor']
        self.assertIsNone(plugin._validate_existing_ng_scaling(cluster,
                                                               supervisor_id))

    def test_validate_additional_ng_scaling(self):
        data = {'name': "cluster",
                'plugin_name': "storm",
                'hadoop_version': "0.9.2",
                'node_groups': [
                    {'name': 'main',
                     'flavor_id': '42',
                     'count': 1,
                     'node_processes': ['nimbus']},
                    {'name': 'subordinate',
                     'flavor_id': '42',
                     'count': 1,
                     'node_processes': ['supervisor']},
                    {'name': 'zookeeper',
                     'flavor_id': '42',
                     'count': 1,
                     'node_processes': ['zookeeper']},
                    {'name': 'subordinate2',
                     'flavor_id': '42',
                     'count': 0,
                     'node_processes': ['supervisor']}
                    ]
                }
        cluster = conductor.cluster_create(context.ctx(), data)
        plugin = pb.PLUGINS.get_plugin(cluster.plugin_name)
        supervisor_id = [node.id for node in cluster.node_groups
                         if node.name == 'supervisor']
        self.assertIsNone(plugin._validate_additional_ng_scaling(cluster,
                                                                 supervisor_id)
                          )

    def test_validate_existing_ng_scaling_raises(self):
        data = {'name': "cluster",
                'plugin_name': "storm",
                'hadoop_version': "0.9.2",
                'node_groups': [
                    {'name': 'main',
                     'flavor_id': '42',
                     'count': 1,
                     'node_processes': ['nimbus']},
                    {'name': 'subordinate',
                     'flavor_id': '42',
                     'count': 1,
                     'node_processes': ['supervisor']},
                    {'name': 'zookeeper',
                     'flavor_id': '42',
                     'count': 1,
                     'node_processes': ['zookeeper']}
                    ]
                }
        cluster = conductor.cluster_create(context.ctx(), data)
        plugin = pb.PLUGINS.get_plugin(cluster.plugin_name)
        main_id = [node.id for node in cluster.node_groups
                     if node.name == 'main']
        self.assertRaises(ex.NodeGroupCannotBeScaled,
                          plugin._validate_existing_ng_scaling,
                          cluster, main_id)

    def test_validate_additional_ng_scaling_raises(self):
        data = {'name': "cluster",
                'plugin_name': "storm",
                'hadoop_version': "0.9.2",
                'node_groups': [
                    {'name': 'main',
                     'flavor_id': '42',
                     'count': 1,
                     'node_processes': ['nimbus']},
                    {'name': 'subordinate',
                     'flavor_id': '42',
                     'count': 1,
                     'node_processes': ['supervisor']},
                    {'name': 'zookeeper',
                     'flavor_id': '42',
                     'count': 1,
                     'node_processes': ['zookeeper']},
                    {'name': 'main2',
                     'flavor_id': '42',
                     'count': 0,
                     'node_processes': ['nimbus']}
                    ]
                }
        cluster = conductor.cluster_create(context.ctx(), data)
        plugin = pb.PLUGINS.get_plugin(cluster.plugin_name)
        main_id = [node.id for node in cluster.node_groups
                     if node.name == 'main2']
        self.assertRaises(ex.NodeGroupCannotBeScaled,
                          plugin._validate_existing_ng_scaling,
                          cluster, main_id)

    def test_get_open_port(self):
        plugin_storm = pl.StormProvider()
        cluster = mock.Mock()
        ng = mock.Mock()
        ng.node_processes = ['nimbus']
        cluster.node_groups = [ng]
        ng.cluster = cluster
        ports = plugin_storm.get_open_ports(ng)
        self.assertEqual([8080], ports)
