import sys
import os

# Force Python to look at the current directory structure
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Point to your core config file where celery_app lives
from app.core.celery_config import celery_app

if __name__ == "__main__":
    print("Starting Celery Worker from Python script runner...")
    celery_app.start(argv=["worker", "--loglevel=info", "-P", "solo"])