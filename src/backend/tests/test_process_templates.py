import json
import sys
import unittest
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from auth import hash_password
from database import Base
from models import Agent, ProcessTemplate, Project, ProjectPlan, Task, User
from routers.process_templates import (
    ProcessTemplateCreate,
    ProcessTemplateUpdate,
    TemplateApplyRequest,
    TemplatePromptRequest,
    apply_template,
    create_template,
    delete_template,
    generate_template_prompt,
    get_template,
    list_templates,
    update_template,
    validate_template_json,
)


class ProcessTemplateTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.db = self.SessionLocal()
        self.user = User(id=1, username="owner", password_hash=hash_password("Owner123"), role="user", status="active")
        self.other_user = User(id=2, username="other", password_hash=hash_password("Other123"), role="user", status="active")
        self.db.add(self.user)
        self.db.add(self.other_user)
        self.db.add_all([
            Agent(id=10, name="Claude", slug="claude-a", agent_type="claude", created_by=1),
            Agent(id=11, name="Codex", slug="codex-b", agent_type="codex", created_by=1),
            Agent(id=12, name="Outside", slug="outside", agent_type="codex", created_by=1),
        ])
        self.db.add(Project(
            id=20,
            name="Demo",
            goal="Ship feature",
            collaboration_dir="outputs/proj-20",
            status="planning",
            created_by=1,
            agent_ids_json=json.dumps([
                {"id": 10, "co_located": False},
                {"id": 11, "co_located": False},
            ]),
            task_timeout_minutes=33,
        ))
        self.db.commit()
        self.addCleanup(self.db.close)

    def _template_json(self):
        return {
            "plan_name": "代码审查流程",
            "description": "适用于代码审查",
            "tasks": [
                {
                    "task_code": "T1",
                    "task_name": "初审",
                    "description": "进行初步审查",
                    "assignee": "agent-1",
                    "depends_on": [],
                    "expected_output": "outputs/T1/result.json",
                },
                {
                    "task_code": "T2",
                    "task_name": "复审",
                    "description": "进行复审",
                    "assignee": "agent-2",
                    "depends_on": ["T1"],
                    "expected_output": "outputs/T2/result.json",
                },
            ],
        }

    def test_validate_template_rejects_concrete_assignee(self):
        data = self._template_json()
        data["tasks"][0]["assignee"] = "claude-a"
        with self.assertRaises(HTTPException) as ctx:
            validate_template_json(data)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("agent-N", ctx.exception.detail)

    def test_validate_template_rejects_unknown_dependency(self):
        data = self._template_json()
        data["tasks"][0]["depends_on"] = ["T99"]
        with self.assertRaises(HTTPException) as ctx:
            validate_template_json(data)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("unknown task_code", ctx.exception.detail)

    def test_validate_template_rejects_cyclic_dependency(self):
        data = self._template_json()
        data["tasks"][0]["depends_on"] = ["T2"]
        with self.assertRaises(HTTPException) as ctx:
            validate_template_json(data)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("DAG", ctx.exception.detail)

    def test_validate_template_rejects_absolute_expected_output(self):
        data = self._template_json()
        data["tasks"][0]["expected_output"] = "/tmp/result.json"
        with self.assertRaises(HTTPException) as ctx:
            validate_template_json(data)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("invalid expected_output", ctx.exception.detail)

    def test_create_template_extracts_slots_and_metadata(self):
        response = create_template(
            ProcessTemplateCreate(name="", description="", template_json=self._template_json()),
            self.db,
            self.user,
        )
        self.assertEqual(response.name, "代码审查流程")
        self.assertEqual(response.agent_count, 2)
        self.assertEqual(response.agent_slots, ["agent-1", "agent-2"])

    def test_create_template_saves_normalized_role_descriptions(self):
        response = create_template(
            ProcessTemplateCreate(
                name="",
                description="",
                template_json=self._template_json(),
                agent_roles_description={
                    "agent-1": "  负责初审，适合代码分析 Agent。  ",
                    "agent-2": "",
                    "agent-3": "无效槽位",
                    "agent-4": 123,
                },
            ),
            self.db,
            self.user,
        )

        self.assertEqual(response.agent_roles_description, {"agent-1": "负责初审，适合代码分析 Agent。"})
        stored = self.db.query(ProcessTemplate).filter(ProcessTemplate.id == response.id).one()
        self.assertEqual(json.loads(stored.agent_roles_description_json), {"agent-1": "负责初审，适合代码分析 Agent。"})

    def test_list_and_detail_return_role_descriptions(self):
        created = create_template(
            ProcessTemplateCreate(
                name="",
                description="",
                template_json=self._template_json(),
                agent_roles_description={"agent-1": "负责初审"},
            ),
            self.db,
            self.user,
        )

        detail = get_template(created.id, self.db, self.user)
        listed = list_templates(self.db, self.user)

        self.assertEqual(detail.agent_roles_description, {"agent-1": "负责初审"})
        self.assertEqual(listed[0].agent_roles_description, {"agent-1": "负责初审"})

    def test_generate_prompt_includes_optional_scenario(self):
        response = generate_template_prompt(
            TemplatePromptRequest(scenario="多人代码审查", description="先初审，再复审，最后汇总。"),
            self.user,
        )

        self.assertIn("## 适用场景 / 流程目标上下文", response.prompt)
        self.assertIn("多人代码审查", response.prompt)
        self.assertIn("## 详细流程需求", response.prompt)
        self.assertIn("先初审，再复审，最后汇总。", response.prompt)
        self.assertIn("agent_roles", response.prompt)
        self.assertIn("适合由什么类型的 Agent 担任", response.prompt)

    def test_generate_prompt_allows_empty_scenario(self):
        response = generate_template_prompt(
            TemplatePromptRequest(scenario="", description="先拆解任务，再并行执行。"),
            self.user,
        )

        self.assertNotIn("适用场景 / 流程目标上下文", response.prompt)
        self.assertIn("先拆解任务，再并行执行。", response.prompt)

    def test_update_template_refreshes_metadata_from_new_json_when_fields_empty(self):
        created = create_template(
            ProcessTemplateCreate(name="", description="", template_json=self._template_json()),
            self.db,
            self.user,
        )
        updated_json = self._template_json()
        updated_json["plan_name"] = "更新后的流程"
        updated_json["description"] = "更新后的描述"

        response = update_template(
            created.id,
            ProcessTemplateUpdate(name="", description="", template_json=updated_json),
            self.db,
            self.user,
        )
        self.assertEqual(response.name, "更新后的流程")
        self.assertEqual(response.description, "更新后的描述")

    def test_update_template_drops_roles_for_removed_slots(self):
        created = create_template(
            ProcessTemplateCreate(
                name="",
                description="",
                template_json=self._template_json(),
                agent_roles_description={"agent-1": "负责初审", "agent-2": "负责复审"},
            ),
            self.db,
            self.user,
        )
        updated_json = self._template_json()
        updated_json["tasks"][1]["assignee"] = "agent-3"

        response = update_template(
            created.id,
            ProcessTemplateUpdate(
                name="",
                description="",
                template_json=updated_json,
                agent_roles_description={"agent-2": "旧角色", "agent-3": "负责复审"},
            ),
            self.db,
            self.user,
        )

        self.assertEqual(response.agent_slots, ["agent-1", "agent-3"])
        self.assertEqual(response.agent_roles_description, {"agent-3": "负责复审"})

    def test_update_template_keeps_existing_valid_roles_when_roles_omitted(self):
        created = create_template(
            ProcessTemplateCreate(
                name="",
                description="",
                template_json=self._template_json(),
                agent_roles_description={"agent-1": "负责初审", "agent-2": "负责复审"},
            ),
            self.db,
            self.user,
        )

        response = update_template(
            created.id,
            ProcessTemplateUpdate(name="保留角色说明"),
            self.db,
            self.user,
        )

        self.assertEqual(response.agent_roles_description, {"agent-1": "负责初审", "agent-2": "负责复审"})

    def test_update_template_can_clear_all_role_descriptions(self):
        created = create_template(
            ProcessTemplateCreate(
                name="",
                description="",
                template_json=self._template_json(),
                agent_roles_description={"agent-1": "负责初审", "agent-2": "负责复审"},
            ),
            self.db,
            self.user,
        )

        response = update_template(
            created.id,
            ProcessTemplateUpdate(agent_roles_description={}),
            self.db,
            self.user,
        )

        self.assertEqual(response.agent_roles_description, {})
        stored = self.db.query(ProcessTemplate).filter(ProcessTemplate.id == created.id).one()
        self.assertIsNone(stored.agent_roles_description_json)

    def test_update_template_rejects_empty_name_when_json_has_no_plan_name(self):
        created = create_template(
            ProcessTemplateCreate(name="", description="", template_json=self._template_json()),
            self.db,
            self.user,
        )
        updated_json = self._template_json()
        updated_json["plan_name"] = ""
        with self.assertRaises(HTTPException) as ctx:
            update_template(
                created.id,
                ProcessTemplateUpdate(name="", description="", template_json=updated_json),
                self.db,
                self.user,
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Template name is required", ctx.exception.detail)

    def test_non_creator_cannot_update_or_delete_template(self):
        created = create_template(
            ProcessTemplateCreate(name="", description="", template_json=self._template_json()),
            self.db,
            self.user,
        )
        with self.assertRaises(HTTPException) as update_ctx:
            update_template(
                created.id,
                ProcessTemplateUpdate(name="blocked"),
                self.db,
                self.other_user,
            )
        self.assertEqual(update_ctx.exception.status_code, 403)

        with self.assertRaises(HTTPException) as delete_ctx:
            delete_template(created.id, self.db, self.other_user)
        self.assertEqual(delete_ctx.exception.status_code, 403)

    def test_apply_template_replaces_slots_and_creates_tasks(self):
        template = create_template(
            ProcessTemplateCreate(name="", description="", template_json=self._template_json()),
            self.db,
            self.user,
        )
        response = apply_template(
            template.id,
            20,
            TemplateApplyRequest(slot_agent_ids={"agent-1": 10, "agent-2": 11}),
            self.db,
            self.user,
        )
        self.assertEqual(response.tasks_created, 2)

        tasks = self.db.query(Task).filter(Task.project_id == 20).order_by(Task.task_code.asc()).all()
        self.assertEqual([task.assignee_agent_id for task in tasks], [10, 11])
        self.assertEqual(tasks[0].expected_output_path, "outputs/proj-20/T1/result.json")
        self.assertEqual(tasks[0].timeout_minutes, 33)

    def test_apply_template_rejects_project_status_that_cannot_plan(self):
        project = self.db.query(Project).filter(Project.id == 20).one()
        project.status = "executing"
        self.db.commit()
        template = create_template(
            ProcessTemplateCreate(name="", description="", template_json=self._template_json()),
            self.db,
            self.user,
        )
        with self.assertRaises(HTTPException) as ctx:
            apply_template(
                template.id,
                20,
                TemplateApplyRequest(slot_agent_ids={"agent-1": 10, "agent-2": 11}),
                self.db,
                self.user,
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Cannot apply template", ctx.exception.detail)

    def test_apply_template_rejects_agent_not_in_project(self):
        template = create_template(
            ProcessTemplateCreate(name="", description="", template_json=self._template_json()),
            self.db,
            self.user,
        )
        with self.assertRaises(HTTPException) as ctx:
            apply_template(
                template.id,
                20,
                TemplateApplyRequest(slot_agent_ids={"agent-1": 10, "agent-2": 12}),
                self.db,
                self.user,
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("must belong to the project", ctx.exception.detail)

    def test_apply_template_deletes_old_unselected_candidate_plans_only(self):
        self.db.add_all([
            ProjectPlan(
                id=100,
                project_id=20,
                plan_type="candidate",
                status="completed",
                is_selected=False,
                plan_json=json.dumps({"tasks": []}),
            ),
            ProjectPlan(
                id=101,
                project_id=20,
                plan_type="final",
                status="final",
                is_selected=True,
                plan_json=json.dumps({"tasks": []}),
            ),
        ])
        self.db.commit()
        template = create_template(
            ProcessTemplateCreate(name="", description="", template_json=self._template_json()),
            self.db,
            self.user,
        )
        response = apply_template(
            template.id,
            20,
            TemplateApplyRequest(slot_agent_ids={"agent-1": 10, "agent-2": 11}),
            self.db,
            self.user,
        )
        self.assertEqual(response.tasks_created, 2)
        self.assertIsNone(self.db.query(ProjectPlan).filter(ProjectPlan.id == 100).first())
        self.assertIsNotNone(self.db.query(ProjectPlan).filter(ProjectPlan.id == 101).first())

    def test_apply_template_rejects_duplicate_agent_mapping(self):
        template = create_template(
            ProcessTemplateCreate(name="", description="", template_json=self._template_json()),
            self.db,
            self.user,
        )
        with self.assertRaises(HTTPException) as ctx:
            apply_template(
                template.id,
                20,
                TemplateApplyRequest(slot_agent_ids={"agent-1": 10, "agent-2": 10}),
                self.db,
                self.user,
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("cannot be mapped", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
