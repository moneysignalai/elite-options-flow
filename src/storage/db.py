from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from loguru import logger

from src.storage import models


def init_engine(database_url: str):
    engine = create_engine(database_url)
    models.Base.metadata.create_all(engine)
    return engine


def get_session_factory(engine):
    return sessionmaker(bind=engine)
