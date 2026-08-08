from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from core.config import settings

engine = create_engine(settings.POSTGRES_DATABASE_URI, echo=(settings.ENV == "dev"))

Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

session = Session()

Base = declarative_base()


def get_db():
    db = Session()
    try:
        yield db
    finally:
        db.close()
