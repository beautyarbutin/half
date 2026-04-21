import json
import sys
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import database
from auth import hash_password
from models import Agent, Base, Project, ProjectPlan, User
from routers import auth as auth_router
from routers import plans as plans_router


class PlanPromptReuseTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

        app = FastAPI()
        app.include_router(auth_router.router)
        app.include_router(plans_router.router)

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[database.get_db] = override_get_db
        self.client = TestClient(app)

        with self.SessionLocal() as db:
            user = User(username="alice", password_hash=hash_password("Alice123"))
            db.add(user)
            db.flush()
            db.add_all([
                Agent(
                    name="Planner",
                    slug="planner",
                    agent_type="codex",
                    model_name="gpt-5-codex",
                    created_by=user.id,
                ),
                Agent(
                    name="Reviewer",
                    slug="reviewer",
                    agent_type="claude",
                    model_name="claude-sonnet",
                    created_by=user.id,
                ),
            ])
            db.flush()
            db.add(Project(
                name="Demo",
                goal="Build the project",
                collaboration_dir="plans",
                agent_ids_json="[1, 2]",
                created_by=user.id,
            ))
            db.commit()

        response = self.client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "Alice123"},
        )
        self.assertEqual(response.status_code, 200)
        self.headers = {"Authorization": f"Bearer {response.json()['token']}"}

    def _generate_prompt(self, agent_ids=None, selected_models=None):
        response = self.client.post(
            "/api/projects/1/plans/generate-prompt",
            json={
                "selected_agent_ids": agent_ids or [1],
                "include_usage": False,
                "selected_agent_models": selected_models or {},
            },
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_generate_prompt_reuses_unsubmitted_pending_plan(self):
        first = self._generate_prompt()
        second = self._generate_prompt(agent_ids=[1, 2])

        self.assertEqual(second["plan_id"], first["plan_id"])
        self.assertEqual(second["source_path"], first["source_path"])
        self.assertIn(first["source_path"], second["prompt"])

        with self.SessionLocal() as db:
            plans = db.query(ProjectPlan).filter(ProjectPlan.project_id == 1).all()
            self.assertEqual(len(plans), 1)
            self.assertEqual(json.loads(plans[0].selected_agent_ids_json), [1, 2])
            self.assertEqual(plans[0].source_path, first["source_path"])

    def test_generate_prompt_keeps_existing_source_path_when_project_dir_changes(self):
        first = self._generate_prompt()

        with self.SessionLocal() as db:
            project = db.query(Project).filter(Project.id == 1).one()
            project.collaboration_dir = "changed-dir"
            db.commit()

        second = self._generate_prompt()

        self.assertEqual(second["plan_id"], first["plan_id"])
        self.assertEqual(second["source_path"], first["source_path"])
        self.assertIn(first["source_path"], second["prompt"])
        self.assertNotIn("changed-dir/plan-", second["prompt"])

    def test_generate_prompt_updates_models_when_reusing_pending_plan(self):
        first = self._generate_prompt(agent_ids=[1], selected_models={"1": "gpt-5-codex"})
        second = self._generate_prompt(agent_ids=[2], selected_models={"2": "claude-sonnet"})

        self.assertEqual(second["plan_id"], first["plan_id"])
        with self.SessionLocal() as db:
            plan = db.query(ProjectPlan).filter(ProjectPlan.id == first["plan_id"]).one()
            self.assertEqual(json.loads(plan.selected_agent_ids_json), [2])
            self.assertEqual(json.loads(plan.selected_agent_models_json), {"2": "claude-sonnet"})
            self.assertIn("Reviewer", plan.prompt_text)
            self.assertNotIn("Planner", plan.prompt_text)

    def test_generate_prompt_creates_new_plan_after_dispatch(self):
        first = self._generate_prompt()

        dispatch = self.client.post(
            f"/api/projects/1/plans/{first['plan_id']}/dispatch",
            headers=self.headers,
        )
        self.assertEqual(dispatch.status_code, 200, dispatch.text)
        self.assertEqual(dispatch.json()["status"], "running")

        second = self._generate_prompt()

        self.assertNotEqual(second["plan_id"], first["plan_id"])
        self.assertNotEqual(second["source_path"], first["source_path"])
        with self.SessionLocal() as db:
            plans = db.query(ProjectPlan).filter(ProjectPlan.project_id == 1).order_by(ProjectPlan.id.asc()).all()
            self.assertEqual(len(plans), 2)
            self.assertEqual(plans[0].status, "running")
            self.assertEqual(plans[1].status, "pending")


if __name__ == "__main__":
    unittest.main()
