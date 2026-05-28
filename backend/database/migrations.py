from database.connection import engine, Base
import database.models

print("Initializing Maya AI Database...")
Base.metadata.create_all(bind=engine)
print("Database initialized successfully.")
