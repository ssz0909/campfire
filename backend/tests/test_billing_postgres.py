"""Exercise actual row locks on a disposable local PostgreSQL cluster."""
import shutil
import socket
import subprocess
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.billing import SubscriptionPeriod
from app.services import billing
from app.services.billing_catalog import Catalog,DEFAULT,save_catalog
from tests.conftest import create_test_company,create_test_user
from tests.test_billing import order


@contextmanager
def local_postgres():
    initdb,pg_ctl=shutil.which('initdb'),shutil.which('pg_ctl')
    if not initdb or not pg_ctl:pytest.skip('Local PostgreSQL binaries not installed')
    root=Path(tempfile.mkdtemp(prefix='cf-pay-',dir='/tmp'))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    running=False
    try:
        subprocess.run([initdb,'-D',str(root/'data'),'-A','trust','-U','billingtest','--no-locale','-E','UTF8'],check=True,capture_output=True)
        subprocess.run([pg_ctl,'-D',str(root/'data'),'-l',str(root/'postgres.log'),'-o',f"-h '' -k {root} -p {port}",'-w','start'],check=True,capture_output=True)
        running=True
        yield f'postgresql://billingtest@/postgres?host={root}&port={port}'
    finally:
        if running:subprocess.run([pg_ctl,'-D',str(root/'data'),'-m','immediate','stop'],capture_output=True)
        shutil.rmtree(root,ignore_errors=True)


def test_concurrent_reservations_and_duplicate_payment_grant(db):
    with local_postgres() as url:
        engine=create_engine(url)
        Base.metadata.create_all(engine)
        # Exercise the exact versioned migration against the disposable cluster.
        import importlib.util
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        path=Path(__file__).resolve().parents[1]/'alembic/versions/20261118_billing.py'
        spec=importlib.util.spec_from_file_location('billing_migration_test',path)
        migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        with engine.begin() as connection:
            migration.op=Operations(MigrationContext.configure(connection))
            migration.downgrade();migration.upgrade()
        sessions=sessionmaker(bind=engine)
        try:
            with sessions() as session:
                user=create_test_user(session,email='locks@example.test')
                company=create_test_company(session,user,slug='billing-lock-test')
                company_id=company.id
                config={**DEFAULT,'enforce_billing':True}
                save_catalog(session,Catalog(**config));session.commit()
                payment=order(session,user,company)
                details=(payment.order_no,payment.channel,'pg-payment',payment.amount_fen,payment.merchant_snapshot)
            barrier=Barrier(2)
            def pay():
                with sessions() as session:
                    barrier.wait(timeout=10)
                    billing.settle_order(session,*details)
                    return 'paid'
            with ThreadPoolExecutor(max_workers=2) as pool:
                assert list(pool.map(lambda _:pay(),range(2)))==['paid','paid']
            with sessions() as session:assert session.query(SubscriptionPeriod).count()==1
            barrier=Barrier(2)
            def reserve():
                with sessions() as session:
                    barrier.wait(timeout=10)
                    try:
                        billing.reserve(session,company_id,'video:'+uuid.uuid4().hex,'video',video_seconds=100)
                        return 'reserved'
                    except HTTPException as exc:
                        assert exc.status_code==402
                        session.rollback()
                        return 'insufficient'
            with ThreadPoolExecutor(max_workers=2) as pool:
                assert sorted(pool.map(lambda _:reserve(),range(2)))==['insufficient','reserved']
            with sessions() as session:
                period=billing.active_period(session,company_id)
                assert period.reserved_units==5000*1_000_000
                assert period.used_units+period.reserved_units<=period.included_units
        finally:engine.dispose()
