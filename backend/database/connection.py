import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.config.runtime_paths import DATA_DIR


DATA_DIR.mkdir(parents=True, exist_ok=True)
_DATABASE_FILE = DATA_DIR / "memory.db"
DB_PATH = os.getenv("MAYA_DATABASE_URL", f"sqlite:///{_DATABASE_FILE.as_posix()}")

# Validate SQLite database URL path access
if DB_PATH.startswith("sqlite:///"):
    raw_db_path = DB_PATH.replace("sqlite:///", "")
    if raw_db_path != ":memory:":
        try:
            db_file_path = os.path.abspath(raw_db_path)
            parent_dir = os.path.dirname(db_file_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
        except Exception as e:
            raise RuntimeError(
                f"[DATABASE ERROR] Cannot initialize database at path '{raw_db_path}'. "
                f"Parent directory is inaccessible or path is invalid: {e}"
            )

engine = create_engine(DB_PATH, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
