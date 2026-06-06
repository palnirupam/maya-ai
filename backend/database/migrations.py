from database.connection import engine, Base
import database.models
from sqlalchemy import inspect, text

print("Initializing Maya AI Database...")
Base.metadata.create_all(bind=engine)

# Check and execute migrations for long_term_memory new columns
try:
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns('long_term_memory')]
    new_cols = {
        'vector': 'TEXT',
        'embedding_model': 'VARCHAR',
        'last_accessed': 'DATETIME',
        'retrieval_count': 'INTEGER DEFAULT 0'
    }
    for col_name, col_type in new_cols.items():
        if col_name not in columns:
            print(f"Adding column '{col_name}' to long_term_memory table...")
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE long_term_memory ADD COLUMN {col_name} {col_type}"))
except Exception as e:
    print(f"Migration error: {e}")

print("Database initialized successfully.")
