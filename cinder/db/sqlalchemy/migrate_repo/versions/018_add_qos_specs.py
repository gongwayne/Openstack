# Copyright (C) 2013 eBay Inc.
# Copyright (C) 2013 OpenStack Foundation
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

from sqlalchemy import Boolean, Column, DateTime
from sqlalchemy import ForeignKey, MetaData, String, Table


def upgrade(migrate_engine):
    """Add volume_type_rate_limit table."""
    meta = MetaData()
    meta.bind = migrate_engine

    quality_of_service_specs = Table(
        'quality_of_service_specs', meta,
        Column('created_at', DateTime(timezone=False)),
        Column('updated_at', DateTime(timezone=False)),
        Column('deleted_at', DateTime(timezone=False)),
        Column('deleted', Boolean(create_constraint=True, name=None)),
        Column('id', String(36), primary_key=True, nullable=False),
        Column('specs_id', String(36),
               ForeignKey('quality_of_service_specs.id')),
        Column('key', String(255)),
        Column('value', String(255)),
        mysql_engine='InnoDB',
        mysql_charset='utf8'
    )

    quality_of_service_specs.create()

    volume_types = Table('volume_types', meta, autoload=True)
    qos_specs_id = Column('qos_specs_id', String(36),
                          ForeignKey('quality_of_service_specs.id'))

    volume_types.create_column(qos_specs_id)
    volume_types.update().values(qos_specs_id=None).execute()
