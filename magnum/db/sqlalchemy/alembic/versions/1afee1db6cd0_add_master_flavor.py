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
"""Add main flavor

Revision ID: 1afee1db6cd0
Revises: 3a938526b35d
Create Date: 2015-02-27 14:53:38.042900

"""

# revision identifiers, used by Alembic.
revision = '1afee1db6cd0'
down_revision = '35cff7c86221'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('baymodel', sa.Column('main_flavor_id',
                  sa.String(length=255), nullable=True))
