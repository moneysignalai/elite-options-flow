"""create alerts tables"""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'alerts',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('underlying', sa.String(length=16), nullable=False),
        sa.Column('option_ticker', sa.String(length=64), nullable=False),
        sa.Column('call_put', sa.String(length=4), nullable=False),
        sa.Column('strike', sa.Float, nullable=False),
        sa.Column('expiry', sa.Date, nullable=False),
        sa.Column('dte', sa.Integer, nullable=False),
        sa.Column('premium_total', sa.Float, nullable=False),
        sa.Column('contracts_total', sa.Float, nullable=False),
        sa.Column('prints_count', sa.Integer, nullable=False),
        sa.Column('duration_sec', sa.Float, nullable=False),
        sa.Column('ask_side_ratio', sa.Float, nullable=False),
        sa.Column('sweep_score', sa.Float, nullable=True),
        sa.Column('oi', sa.Float, nullable=True),
        sa.Column('vol_oi_ratio', sa.Float, nullable=True),
        sa.Column('otm_pct', sa.Float, nullable=True),
        sa.Column('setup_type', sa.String(length=32), nullable=False),
        sa.Column('score_total', sa.Float, nullable=False),
        sa.Column('score_components_json', sa.Text, nullable=False),
        sa.Column('tags_json', sa.Text, nullable=False),
        sa.Column('template_type', sa.String(length=32), nullable=False),
        sa.Column('cluster_key', sa.String(length=128), nullable=False, index=True),
    )
    op.create_table(
        'dedupe_state',
        sa.Column('cluster_key', sa.String(length=128), primary_key=True),
        sa.Column('last_alert_ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_score', sa.Float, nullable=False),
        sa.Column('last_premium', sa.Float, nullable=False),
    )


def downgrade():
    op.drop_table('dedupe_state')
    op.drop_table('alerts')
