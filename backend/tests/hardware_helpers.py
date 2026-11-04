"""Test setup for the hardware-only hold scope, without changing routing facts."""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.models.category import TicketCategory
from app.models.ticket import Ticket

async def use_hardware_category(env, ticket_id):
    factory = async_sessionmaker(env["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        if await db.get(TicketCategory, 2301) is None:
            db.add(TicketCategory(id=2301, name="业务保障", level=1))
            await db.flush()
        if await db.get(TicketCategory, 2322) is None:
            db.add(TicketCategory(id=2322, parent_id=2301, name="硬件故障", level=2))
            await db.flush()
        ticket = await db.get(Ticket, ticket_id)
        ticket.category_id = 2322
        await db.commit()
