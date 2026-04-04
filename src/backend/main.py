import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import inspect, text
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import engine, SessionLocal, Base
from models import User
from auth import hash_password
from routers import auth as auth_router
from routers import agents as agents_router
from routers import projects as projects_router
from routers import plans as plans_router
from routers import tasks as tasks_router
from routers import polling as polling_router
from services.polling_service import polling_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("half")


def ensure_schema_updates():
    inspector = inspect(engine)
    required_columns = {
        "agents": {
            "capability": "TEXT",
            "short_term_reset_at": "DATETIME",
            "short_term_reset_interval_hours": "INTEGER",
            "long_term_reset_at": "DATETIME",
            "long_term_reset_interval_days": "INTEGER",
        },
        "projects": {
            "collaboration_dir": "TEXT",
        },
        "project_plans": {
            "prompt_text": "TEXT",
            "status": "TEXT DEFAULT 'completed'",
            "source_path": "TEXT",
            "include_usage": "BOOLEAN DEFAULT 0",
            "selected_agent_ids_json": "TEXT DEFAULT '[]'",
            "dispatched_at": "DATETIME",
            "detected_at": "DATETIME",
            "last_error": "TEXT",
        },
    }

    with engine.begin() as conn:
        for table_name, columns in required_columns.items():
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_type in columns.items():
                if column_name not in existing:
                    conn.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}'))
                    logger.info("Added missing column %s.%s", table_name, column_name)


def init_db():
    Base.metadata.create_all(bind=engine)
    ensure_schema_updates()
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin = User(
                username="admin",
                password_hash=hash_password(settings.ADMIN_PASSWORD),
            )
            db.add(admin)
            db.commit()
            logger.info("Default admin user created")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    logger.info("Database initialized")
    poller_task = asyncio.create_task(polling_loop(settings.POLL_INTERVAL_SECONDS))
    logger.info("Background poller started")
    yield
    # Shutdown
    poller_task.cancel()
    try:
        await poller_task
    except asyncio.CancelledError:
        pass
    logger.info("Background poller stopped")


app = FastAPI(title="HALF Backend", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(agents_router.router)
app.include_router(projects_router.router)
app.include_router(plans_router.router)
app.include_router(tasks_router.router)
app.include_router(polling_router.router)


@app.get("/")
def root():
    return {"name": "HALF Backend", "version": "1.0.0"}
