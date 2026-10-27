"""业财对账由部门当前有效的默认处理人承接，不依赖建单人选销售。"""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.dispatch_chain import prescribe_dept


def reconciliation_steps() -> list[dict]:
    return [
        {"order": 1, "department_code": "经营管理部"},
        {"order": 2, "department_code": "财务"},
    ]


async def reconciliation_assignment(db: AsyncSession, department: str) -> dict:
    rx = await prescribe_dept(db, department)
    if not rx or not rx["owner_id"]:
        raise HTTPException(422, detail=f"{department}尚未配置有效处理人，请联系管理员")
    return rx
