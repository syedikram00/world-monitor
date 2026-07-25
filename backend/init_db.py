import time
from sqlalchemy.exc import OperationalError

from database import engine
from models import Base

for attempt in range(10):
    try:
        Base.metadata.create_all(bind=engine)
        print("Tables created successfully!")
        break
    except OperationalError:
        print("Database not ready, retrying...")
        time.sleep(2)
else:
    raise RuntimeError("Could not connect to PostgreSQL.")