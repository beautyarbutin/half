from sqlalchemy.orm import Session

from models import GlobalSetting


PLAN_CO_LOCATION_GUIDANCE_KEY = "plan_co_location_guidance"

DEFAULT_PLAN_CO_LOCATION_GUIDANCE = """## 同服务器分配规则

每个参与 Agent 标注了“同服务器：是/否”，请在分配任务时遵守以下规则：

1. 必须分配给同服务器 Agent 的任务：重新部署系统、重启服务、查看/修改本地配置文件、读取运行时日志、访问本地数据库等需要直接操作项目部署环境的任务。
2. 优先分配给同服务器 Agent 的任务：复现线上 bug、运行时状态验证、性能测试、本地文件读写等受益于本地访问的任务。
3. 无同机要求的任务：代码编写、文档撰写、方案设计、代码审查等不依赖本地环境的任务，可分配给任何 Agent。
4. 如果参与 Agent 中没有同服务器的，但任务需要同机执行，仍分配给最合适的 Agent，并在任务描述中标注“⚠ 该任务需要同服务器 Agent 执行，当前 assignee 非同服务器，可能无法完成”。
"""


def normalize_plan_co_location_guidance(value: str | None) -> str:
    if value is None or not value.strip():
        return DEFAULT_PLAN_CO_LOCATION_GUIDANCE
    return value


def validate_plan_co_location_guidance(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("co_location_guidance must not be empty")
    return value


def get_plan_co_location_guidance(db: Session) -> str:
    setting = db.query(GlobalSetting).filter(GlobalSetting.key == PLAN_CO_LOCATION_GUIDANCE_KEY).first()
    if not setting:
        return DEFAULT_PLAN_CO_LOCATION_GUIDANCE
    return normalize_plan_co_location_guidance(setting.value)


def upsert_plan_co_location_guidance(db: Session, value: object) -> str:
    guidance = validate_plan_co_location_guidance(value)
    setting = db.query(GlobalSetting).filter(GlobalSetting.key == PLAN_CO_LOCATION_GUIDANCE_KEY).first()
    if not setting:
        setting = GlobalSetting(
            key=PLAN_CO_LOCATION_GUIDANCE_KEY,
            value=guidance,
            description="Planning prompt guidance for co-located agent assignment",
        )
        db.add(setting)
    else:
        setting.value = guidance
    db.commit()
    return guidance
