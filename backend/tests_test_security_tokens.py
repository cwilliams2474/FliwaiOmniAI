from datetime import datetime, timedelta
from app.time_utils import utcnow
from app.database.session import Base
from app.models.core import SecurityToken
from app.security_tokens import create_security_token, consume_security_token
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

def db_session():
    engine=create_engine('sqlite:///:memory:'); Base.metadata.create_all(engine); return sessionmaker(bind=engine)()

def test_security_token_is_one_time():
    db=db_session(); raw,row=create_security_token(db,'password_reset',email='x@example.com'); db.commit()
    assert raw not in row.token_hash
    assert consume_security_token(db,raw,'password_reset') is not None
    db.commit()
    assert consume_security_token(db,raw,'password_reset') is None

def test_expired_security_token_rejected():
    db=db_session(); raw,row=create_security_token(db,'password_reset',email='x@example.com'); row.expires_at=utcnow()-timedelta(seconds=1); db.commit()
    assert consume_security_token(db,raw,'password_reset') is None
