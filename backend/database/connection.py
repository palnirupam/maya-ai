import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.config.runtime_paths import DATA_DIR


DATA_DIR.mkdir(parents=True, exist_ok=True)
_DATABASE_FILE = DATA_DIR / "memory.db"
DB_PATH = os.getenv("MAYA_DATABASE_URL", f"sqlite:///{_DATABASE_FILE.as_posix()}")

engine = create_engine(DB_PATH, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
