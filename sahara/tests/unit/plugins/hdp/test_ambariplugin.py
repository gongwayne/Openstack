# Copyright (c) 2013 Hortonworks, Inc.
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
import pkg_resources as pkg
import testtools

from sahara.conductor import resource as r
from sahara.plugins import base as pb
from sahara.plugins import exceptions as ex
from sahara.plugins.hdp import ambariplugin as ap
from sahara.plugins.hdp import clusterspec as cs
from sahara.tests.unit import base as sahara_base
import sahara.tests.unit.plugins.hdp.hdp_test_base as base
from sahara.utils import edp
from sahara import version


GET_REST_REQ = ("sahara.plugins.hdp.versions.version_2_0_6.versionhandler."
                "AmbariClient._get_http_session")


def create_cluster_template(ctx, dct):
    return r.ClusterTemplateResource(dct)


class AmbariPluginTest(sahara_base.SaharaTestCase):
    def setUp(self):
        super(AmbariPluginTest, self).setUp()
        pb.setup_plugins()

    def test_get_node_processes(self):
        plugin = ap.AmbariPlugin()
        service_components = plugin.get_node_processes('2.0.6')
        self.assertEqual({
            'YARN': ['RESOURCEMANAGER', 'YARN_CLIENT', 'NODEMANAGER'],
            'GANGLIA': ['GANGLIA_SERVER'],
            'HUE': ['HUE'],
            'HIVE': ['HIVE_SERVER', 'HIVE_METASTORE', 'HIVE_CLIENT',
                     'MYSQL_SERVER'],
            'OOZIE': ['OOZIE_SERVER', 'OOZIE_CLIENT'],
            'HDFS': ['NAMENODE', 'DATANODE', 'SECONDARY_NAMENODE',
                     'HDFS_CLIENT', 'JOURNALNODE', 'ZKFC'],
            'SQOOP': ['SQOOP'],
            'MAPREDUCE2': ['HISTORYSERVER', 'MAPREDUCE2_CLIENT'],
            'ZOOKEEPER': ['ZOOKEEPER_SERVER', 'ZOOKEEPER_CLIENT'],
            'HBASE': ['HBASE_MASTER', 'HBASE_REGIONSERVER', 'HBASE_CLIENT'],
            'HCATALOG': ['HCAT'],
            'NAGIOS': ['NAGIOS_SERVER'],
            'AMBARI': ['AMBARI_SERVER'],
            'WEBHCAT': ['WEBHCAT_SERVER'],
            'PIG': ['PIG']}, service_components)

    def test_convert(self):
        plugin = ap.AmbariPlugin()
        cluster_config_file = pkg.resource_string(
            version.version_info.package,
            'plugins/hdp/versions/version_2_0_6/resources/'
            'default-cluster.template')
        cluster = plugin.convert(cluster_config_file, 'ambari', '2.0.6',
                                 'test-plugin', create_cluster_template)
        normalized_config = cs.ClusterSpec(cluster_config_file).normalize()

        self.assertEqual(normalized_config.hadoop_version,
                         cluster.hadoop_version)
        self.assertEqual(len(normalized_config.node_groups),
                         len(cluster.node_groups))

    @mock.patch(GET_REST_REQ)
    def test__set_ambari_credentials__admin_only(self, client):
        client.side_effect = self._get_test_request
        self.requests = []
        plugin = ap.AmbariPlugin()

        cluster_config_file = pkg.resource_string(
            version.version_info.package,
            'plugins/hdp/versions/version_2_0_6/resources/'
            'default-cluster.template')
        cluster_spec = cs.ClusterSpec(cluster_config_file)

        ambari_info = ap.AmbariInfo(TestHost('111.11.1111'),
                                    '8080', 'admin', 'old-pwd')
        plugin._set_ambari_credentials(cluster_spec, ambari_info, '2.0.6')

        self.assertEqual(1, len(self.requests))
        request = self.requests[0]
        self.assertEqual('put', request.method)
        self.assertEqual('http://111.11.1111:8080/api/v1/users/admin',
                         request.url)
        self.assertEqual('{"Users":{"roles":"admin","password":"admin",'
                         '"old_password":"old-pwd"} }', request.data)
        self.assertEqual(('admin', 'old-pwd'), request.auth)
        self.assertEqual('admin', ambari_info.user)
        self.assertEqual('admin', ambari_info.password)

    @mock.patch(GET_REST_REQ)
    def test__set_ambari_credentials__new_user_no_admin(self, client):
        self.requests = []
        plugin = ap.AmbariPlugin()
        client.side_effect = self._get_test_request

        cluster_config_file = pkg.resource_string(
            version.version_info.package,
            'plugins/hdp/versions/version_2_0_6/resources/'
            'default-cluster.template')
        cluster_spec = cs.ClusterSpec(cluster_config_file)

        for service in cluster_spec.services:
            if service.name == 'AMBARI':
                user = service.users[0]
                user.name = 'test'
                user.password = 'test_pw'

        ambari_info = ap.AmbariInfo(TestHost('111.11.1111'), '8080',
                                    'admin', 'old-pwd')
        plugin._set_ambari_credentials(cluster_spec, ambari_info, '2.0.6')
        self.assertEqual(2, len(self.requests))

        request = self.requests[0]
        self.assertEqual('post', request.method)
        self.assertEqual('http://111.11.1111:8080/api/v1/users/test',
                         request.url)
        self.assertEqual('{"Users":{"password":"test_pw","roles":"admin"'
                         '} }', request.data)
        self.assertEqual(('admin', 'old-pwd'), request.auth)

        request = self.requests[1]
        self.assertEqual('delete', request.method)
        self.assertEqual('http://111.11.1111:8080/api/v1/users/admin',
                         request.url)
        self.assertIsNone(request.data)
        self.assertEqual(('test', 'test_pw'), request.auth)
        self.assertEqual('test', ambari_info.user)
        self.assertEqual('test_pw', ambari_info.password)

    @mock.patch(GET_REST_REQ)
    def test__set_ambari_credentials__new_user_with_admin(self, client):
        self.requests = []
        plugin = ap.AmbariPlugin()
        client.side_effect = self._get_test_request

        cluster_config_file = pkg.resource_string(
            version.version_info.package,
            'plugins/hdp/versions/version_2_0_6/resources/'
            'default-cluster.template')
        cluster_spec = cs.ClusterSpec(cluster_config_file)

        for service in cluster_spec.services:
            if service.name == 'AMBARI':
                new_user = cs.User('test', 'test_pw', ['user'])
                service.users.append(new_user)

        ambari_info = ap.AmbariInfo(TestHost('111.11.1111'), '8080',
                                    'admin', 'old-pwd')
        plugin._set_ambari_credentials(cluster_spec, ambari_info, '2.0.6')
        self.assertEqual(2, len(self.requests))

        request = self.requests[0]
        self.assertEqual('put', request.method)
        self.assertEqual('http://111.11.1111:8080/api/v1/users/admin',
                         request.url)
        self.assertEqual('{"Users":{"roles":"admin","password":"admin",'
                         '"old_password":"old-pwd"} }', request.data)
        self.assertEqual(('admin', 'old-pwd'), request.auth)

        request = self.requests[1]
        self.assertEqual('post', request.method)
        self.assertEqual('http://111.11.1111:8080/api/v1/users/test',
                         request.url)
        self.assertEqual('{"Users":{"password":"test_pw","roles":"user"} }',
                         request.data)
        self.assertEqual(('admin', 'admin'), request.auth)

        self.assertEqual('admin', ambari_info.user)
        self.assertEqual('admin', ambari_info.password)

    @mock.patch(GET_REST_REQ)
    @testtools.skip("test failure because of #1325108")
    def test__set_ambari_credentials__no_admin_user(self, client):
        self.requests = []
        plugin = ap.AmbariPlugin()
        client.side_effect = self._get_test_request

        cluster_config_file = pkg.resource_string(
            version.version_info.package,
            'plugins/hdp/versions/version_2_0_6/resources/'
            'default-cluster.template')
        cluster_spec = cs.ClusterSpec(cluster_config_file)

        for service in cluster_spec.services:
            if service.name == 'AMBARI':
                user = service.users[0]
                user.name = 'test'
                user.password = 'test_pw'
                user.groups = ['user']

        ambari_info = ap.AmbariInfo(TestHost('111.11.1111'),
                                    '8080', 'admin', 'old-pwd')

        self.assertRaises(ex.HadoopProvisionError,
                          plugin._set_ambari_credentials,
                          cluster_spec, ambari_info, '2.0.6')

    @mock.patch("sahara.utils.openstack.nova.get_instance_info",
                base.get_instance_info)
    @mock.patch('sahara.plugins.hdp.versions.version_2_0_6.services.'
                'HdfsService._get_swift_properties', return_value=[])
    def test__get_ambari_info(self, patched):
        cluster_config_file = pkg.resource_string(
            version.version_info.package,
            'plugins/hdp/versions/version_2_0_6/resources/'
            'default-cluster.template')

        test_host = base.TestServer(
            'host1', 'test-master', '11111', 3, '111.11.1111',
            '222.11.1111')

        node_group = base.TestNodeGroup(
            'ng1', [test_host], ["AMBARI_SERVER", "NAMENODE", "DATANODE",
                                 'RESOURCEMANAGER', 'YARN_CLIENT',
                                 'NODEMANAGER',
                                 'HISTORYSERVER', 'MAPREDUCE2_CLIENT',
                                 'ZOOKEEPER_SERVER', 'ZOOKEEPER_CLIENT'])
        cluster = base.TestCluster([node_group])
        cluster_config = cs.ClusterSpec(cluster_config_file)
        cluster_config.create_operational_config(cluster, [])
        plugin = ap.AmbariPlugin()

        # change port
        cluster_config.configurations['ambari']['server.port'] = '9000'

        ambari_info = plugin.get_ambari_info(cluster_config)
        self.assertEqual('9000', ambari_info.port)

        # remove port
        del cluster_config.configurations['ambari']['server.port']
        ambari_info = plugin.get_ambari_info(cluster_config)

        self.assertEqual('8080', ambari_info.port)

    def test_update_ambari_info_credentials(self):
        plugin = ap.AmbariPlugin()

        cluster_config_file = pkg.resource_string(
            version.version_info.package,
            'plugins/hdp/versions/version_2_0_6/resources/'
            'default-cluster.template')
        cluster_spec = cs.ClusterSpec(cluster_config_file)

        ambari_info = ap.AmbariInfo(TestHost('111.11.1111'),
                                    '8080', 'admin', 'old-pwd')
        plugin._update_ambari_info_credentials(cluster_spec, ambari_info)

        self.assertEqual('admin', ambari_info.user)
        self.assertEqual('admin', ambari_info.password)

    def test_get_oozie_server(self):
        test_host = base.TestServer(
            'host1', 'test-master', '11111', 3, '111.11.1111',
            '222.11.1111')

        node_group = base.TestNodeGroup(
            'ng1', [test_host], ["AMBARI_SERVER", "NAMENODE", "DATANODE",
                                 "OOZIE_SERVER"])
        cluster = base.TestCluster([node_group])
        cluster.hadoop_version = '2.0.6'
        plugin = ap.AmbariPlugin()

        self.assertIsNotNone(plugin.get_edp_engine(
            cluster, edp.JOB_TYPE_PIG).get_oozie_server(cluster))

        node_group = base.TestNodeGroup(
            'ng1', [test_host], ["AMBARI_SERVER", "NAMENODE", "DATANODE",
                                 "NOT_OOZIE"])
        cluster = base.TestCluster([node_group])
        cluster.hadoop_version = '2.0.6'
        self.assertIsNone(plugin.get_edp_engine(
            cluster, edp.JOB_TYPE_PIG).get_oozie_server(cluster))

    @mock.patch('sahara.service.edp.hdfs_helper.create_dir_hadoop2')
    def test_edp206_calls_hadoop2_create_dir(self, create_dir):
        cluster = base.TestCluster([])
        cluster.plugin_name = 'hdp'
        cluster.hadoop_version = '2.0.6'
        plugin = ap.AmbariPlugin()
        plugin.get_edp_engine(cluster, edp.JOB_TYPE_PIG).create_hdfs_dir(
            mock.Mock(), '/tmp')

        self.assertEqual(1, create_dir.call_count)

    def _get_test_request(self, host, port):
        request = base.TestRequest()
        self.requests.append(request)
        return request


class TestHost(object):
    def __init__(self, management_ip, role=None):
        self.management_ip = management_ip
        self.role = role
