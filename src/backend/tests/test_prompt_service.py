import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models import Agent, Project, Task
from services.prompt_service import generate_plan_prompt, generate_task_prompt, resolve_selected_agent_models
from services.prompt_settings import DEFAULT_PLAN_CO_LOCATION_GUIDANCE


class PromptServiceTests(unittest.TestCase):
    def test_resolve_selected_agent_models_prefers_explicit_model(self):
        agent = Agent(
            id=1,
            name="Claude 主力",
            slug="claude-main",
            agent_type="claude",
            model_name="claude-opus-4-1",
            models_json='[{"model_name":"claude-opus-4-1","capability":"复杂规划"},{"model_name":"claude-sonnet-4-5","capability":"代码实现"}]',
        )
        resolved = resolve_selected_agent_models("做复杂规划", [agent], {1: "claude-sonnet-4-5"})
        self.assertEqual(resolved[1], "claude-sonnet-4-5")

    def test_resolve_selected_agent_models_uses_planning_mode_hints(self):
        agent = Agent(
            id=7,
            name="Codex 双模型",
            slug="codex-dual",
            agent_type="codex",
            models_json='[{"model_name":"gpt-5-codex","capability":"复杂规划、高质量"},{"model_name":"codex-mini-latest","capability":"轻量、低成本、响应快"}]',
        )
        cost_resolved = resolve_selected_agent_models("实现普通页面", [agent], {}, "cost_effective")
        speed_resolved = resolve_selected_agent_models("实现普通页面", [agent], {}, "speed")
        quality_resolved = resolve_selected_agent_models("实现普通页面", [agent], {}, "quality")

        self.assertEqual(cost_resolved[7], "codex-mini-latest")
        self.assertEqual(speed_resolved[7], "codex-mini-latest")
        self.assertEqual(quality_resolved[7], "gpt-5-codex")

    def test_generate_plan_prompt_auto_selects_best_matching_model(self):
        project = Project(name="Demo", goal="需要代码实现和任务拆解")
        agent = Agent(
            id=2,
            name="Codex 执行器",
            slug="codex-main",
            agent_type="codex",
            model_name="gpt-5-codex",
            models_json='[{"model_name":"gpt-5-codex","capability":"代码实现、任务拆解"},{"model_name":"codex-mini-latest","capability":"轻量总结"}]',
        )
        prompt, resolved = generate_plan_prompt(project, [agent], "plan-1.json", None, {})
        self.assertEqual(resolved[2], "gpt-5-codex")
        self.assertIn("使用模型：gpt-5-codex", prompt)
        self.assertIn(DEFAULT_PLAN_CO_LOCATION_GUIDANCE, prompt)
        self.assertLess(prompt.index("请根据参与 Agent"), prompt.index("## 同服务器分配规则"))
        self.assertLess(prompt.index("## 同服务器分配规则"), prompt.index("## 输出要求"))

    def test_generate_plan_prompt_includes_planning_mode_guidance(self):
        agent = Agent(
            id=2,
            name="Codex 执行器",
            slug="codex-main",
            agent_type="codex",
            model_name="gpt-5-codex",
        )
        cases = [
            ("balanced", "当前模式：均衡模式", "避免不必要的重复任务和评审链路"),
            ("quality", "当前模式：效果优先", "不要让单个 task 同时绑定多个 assignee"),
            ("cost_effective", "当前模式：性价比高", "用户手动指定的模型优先级最高"),
            ("speed", "当前模式：速度优先", "最大化可并行执行的 task 数量"),
        ]
        for mode, heading, expected in cases:
            with self.subTest(mode=mode):
                project = Project(name="Demo", goal="需要规划", planning_mode=mode)
                prompt, _ = generate_plan_prompt(project, [agent], "plan-1.json", None, {})
                self.assertIn(heading, prompt)
                self.assertIn(expected, prompt)
                self.assertLess(prompt.index("## 规划模式策略"), prompt.index("## 同服务器分配规则"))

    def test_generate_plan_prompt_uses_project_co_location_override(self):
        project = Project(
            name="Demo",
            goal="需要部署和复现线上问题",
            agent_ids_json='[{"id":2,"co_located":false}]',
        )
        agent = Agent(
            id=2,
            name="Codex 执行器",
            slug="codex-main",
            agent_type="codex",
            model_name="gpt-5-codex",
            models_json='[{"model_name":"gpt-5-codex","capability":"部署、日志查看、运行时复现"}]',
            co_located=True,
        )
        prompt, _ = generate_plan_prompt(project, [agent], "plan-1.json", None, {})
        self.assertIn("同服务器：否", prompt)

    def test_generate_plan_prompt_accepts_custom_co_location_guidance(self):
        project = Project(name="Demo", goal="需要部署")
        agent = Agent(id=3, name="Agent", slug="agent", agent_type="codex")
        custom_guidance = "## 自定义同机规则\n只用于本次测试。"
        prompt, _ = generate_plan_prompt(project, [agent], "plan-1.json", None, {}, custom_guidance)
        self.assertIn(custom_guidance, prompt)
        self.assertNotIn("必须分配给同服务器 Agent 的任务", prompt)

    def test_generate_plan_prompt_falls_back_when_guidance_is_blank(self):
        project = Project(name="Demo", goal="需要部署")
        agent = Agent(id=3, name="Agent", slug="agent", agent_type="codex")
        prompt, _ = generate_plan_prompt(project, [agent], "plan-1.json", None, {}, "   ")
        self.assertIn(DEFAULT_PLAN_CO_LOCATION_GUIDANCE, prompt)

    def test_generate_task_prompt_uses_fixed_task_directories(self):
        project = Project(id=4, name="Demo", collaboration_dir="outputs/proj-4-f9a125")
        task = Task(
            project_id=4,
            task_code="TASK-002",
            task_name="处理数据",
            description="处理 TASK-001 输出",
            depends_on_json='["TASK-001"]',
            expected_output_path="outputs/proj-4-f9a125/TASK-002/result.json，包含 task_code 与处理摘要",
        )
        predecessor = Task(
            project_id=4,
            task_code="TASK-001",
            task_name="生成基础数据",
            expected_output_path="outputs/proj-4-f9a125/TASK-001/result.json，包含 task_code 与 base.json 路径",
        )

        class FakeQuery:
            def filter(self, *args, **kwargs):
                return self

            def all(self):
                return [predecessor]

        class FakeSession:
            def query(self, model):
                self.model = model
                return FakeQuery()

        prompt = generate_task_prompt(FakeSession(), project, task)
        self.assertIn("outputs/proj-4-f9a125/TASK-001/", prompt)
        self.assertIn("outputs/proj-4-f9a125/TASK-002/", prompt)
        self.assertIn("result.json.tmp", prompt)
        self.assertIn("原子重命名为 `result.json`", prompt)
        self.assertIn("task_code`、`summary`、`artifacts`", prompt)


if __name__ == "__main__":
    unittest.main()
