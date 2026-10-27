from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.config import settings
from app.models.base import Base  # noqa: F401

# Import all models so autogenerate can detect them
from app.models.user import User  # noqa: F401
from app.models.company import Company, Store, CompanyProduct  # noqa: F401
from app.models.member import CompanyMembership  # noqa: F401
from app.models.role import Role  # noqa: F401
from app.models.asset import Asset  # noqa: F401
from app.models.digital_employee import DigitalEmployee  # noqa: F401
from app.models.task import OperationTask, TaskApprovalRequest  # noqa: F401
from app.models.approval import Approval  # noqa: F401
from app.models.video_project import VideoProject, ProviderTask  # noqa: F401
from app.models.cost import CostRecord  # noqa: F401
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.publishing import PlatformConnection, PublishJob  # noqa: F401
from app.models.subscription import Subscription, UsageRecord  # noqa: F401
from app.connectors.hotel.dingdanlaile import (  # noqa: F401
    HotelConnectorConfig,
    HotelOrder,
    HotelSyncJob,
    PlatformKeyValue,
)

config = context.config

# Override sqlalchemy.url from settings
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
