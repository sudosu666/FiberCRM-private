from datetime import datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_password_hash
from .models import (
    Brigade,
    Building,
    Fiber,
    FiberStatus,
    InfraStatus,
    Muffle,
    Panel,
    Port,
    PortStatus,
    RequestStatus,
    StockItem,
    Task,
    TaskStatus,
    TaskType,
    Tender,
    TenderStatus,
    User,
    UserRole,
    WarehouseRequest,
    WarehouseRequestItem,
    TaskStep,
)

DEMO_USERS = [
    {
        "name": "Олена Диспетчер",
        "phone": "+38000000001",
        "email": "dispatcher@fiberops.local",
        "role": UserRole.Dispatcher,
        "additional_roles": None,
        "password": "dispatcher",
    },
    {
        "name": "BRG-03 Foreman",
        "phone": "+38000000002",
        "email": "builder@fiberops.local",
        "role": UserRole.Builder,
        "additional_roles": UserRole.Welder.value,
        "password": "builder",
    },
    {
        "name": "WL-01 Foreman",
        "phone": "+38000000003",
        "email": "welder@fiberops.local",
        "role": UserRole.Welder,
        "additional_roles": None,
        "password": "welder",
    },
    {
        "name": "CN-01 Foreman",
        "phone": "+38000000004",
        "email": "connector@fiberops.local",
        "role": UserRole.Connector,
        "additional_roles": None,
        "password": "connector",
    },
    {
        "name": "Ірина Склад",
        "phone": "+38000000005",
        "email": "warehouse@fiberops.local",
        "role": UserRole.Warehouse,
        "additional_roles": None,
        "password": "warehouse",
    },
    {
        "name": "Марко Проектувальник",
        "phone": "+38000000006",
        "email": "designer@fiberops.local",
        "role": UserRole.Designer,
        "additional_roles": None,
        "password": "designer",
    },
    {
        "name": "Назар Диспетчер Підключень",
        "phone": "+38000000007",
        "email": "connection.dispatch@fiberops.local",
        "role": UserRole.Dispatcher,
        "additional_roles": UserRole.ConnectionDispatcher.value,
        "password": "connect-dispatch",
    },
]

CLEAN_TENDER_NAME = "Тестовий тендер · Чисті будинки"
CLEAN_BUILDINGS = [
    {"address": "вул. Миру 10 · Харків", "city": "Харків", "entrances": 2, "floors": 9, "flats": 4, "distance": 60},
    {"address": "вул. Перемоги 24 · Харків", "city": "Харків", "entrances": 3, "floors": 12, "flats": 4, "distance": 120},
    {"address": "вул. Квіткова 7 · Харків", "city": "Харків", "entrances": 4, "floors": 10, "flats": 5, "distance": 90},
    {"address": "просп. Науки 33 · Харків", "city": "Харків", "entrances": 2, "floors": 16, "flats": 6, "distance": 150},
    {"address": "вул. Слобідська 5 · Харків", "city": "Харків", "entrances": 1, "floors": 5, "flats": 4, "distance": 45},
]


def demo_login_users() -> list[dict[str, str]]:
    return [
        {
            "name": user["name"],
            "phone": user["phone"],
            "role": user["role"].value,
            "password": user["password"],
        }
        for user in DEMO_USERS
    ]


async def ensure_demo_users(session: AsyncSession) -> dict[str, User]:
    phones = [user["phone"] for user in DEMO_USERS]
    existing_users = (
        await session.scalars(select(User).where(User.phone.in_(phones)))
    ).all()
    users_by_phone = {user.phone: user for user in existing_users}

    for demo_user in DEMO_USERS:
        if demo_user["phone"] in users_by_phone:
            continue
        user = User(
            name=demo_user["name"],
            phone=demo_user["phone"],
            email=demo_user["email"],
            role=demo_user["role"],
            additional_roles=demo_user["additional_roles"],
            password_hash=get_password_hash(demo_user["password"]),
        )
        session.add(user)
        users_by_phone[user.phone] = user

    await session.flush()
    return users_by_phone


async def ensure_clean_tender_buildings(session: AsyncSession) -> None:
    clean_tender = await session.scalar(select(Tender).where(Tender.name == CLEAN_TENDER_NAME))
    if not clean_tender:
        clean_tender = Tender(
            name=CLEAN_TENDER_NAME,
            city="Харків",
            customer="FiberOps Test",
            status=TenderStatus.planning,
            deadline=datetime.utcnow() + timedelta(days=90),
        )
        session.add(clean_tender)
        await session.flush()

    existing_buildings = await session.scalar(
        select(func.count()).select_from(Building).where(Building.tender_id == clean_tender.id)
    )
    if existing_buildings and existing_buildings > 0:
        return

    for item in CLEAN_BUILDINGS:
        session.add(Building(
            tender_id=clean_tender.id,
            address=item["address"],
            city=item["city"],
            entrances_count=item["entrances"],
            floors_count=item["floors"],
            flats_per_floor=item["flats"],
            floor_height_m=2.8,
            panel_every_n_floors=5,
            distance_from_muffle_m=item["distance"],
            cable_reserve_pct=15,
            infrastructure_status=InfraStatus.planned,
        ))
    await session.flush()


async def seed_demo_data(session: AsyncSession) -> None:
    users_by_phone = await ensure_demo_users(session)
    existing = await session.scalar(select(func.count()).select_from(Tender))
    if existing and existing > 0:
        await ensure_clean_tender_buildings(session)
        await session.commit()
        return

    dispatcher = users_by_phone["+38000000001"]
    builder = users_by_phone["+38000000002"]
    welder = users_by_phone["+38000000003"]
    connector = users_by_phone["+38000000004"]

    tender = Tender(
        name='ЖК Сонячний',
        city='Харків',
        status=TenderStatus.in_progress,
        deadline=datetime.utcnow() + timedelta(days=60),
    )
    session.add(tender)
    await session.flush()

    building = Building(
        tender_id=tender.id,
        address='вул. Сонячна 3 · Харків',
        city='Харків',
        entrances_count=4,
        floors_count=9,
        flats_per_floor=4,
        floor_height_m=2.9,
        panel_every_n_floors=5,
        distance_from_muffle_m=80,
        cable_reserve_pct=18,
        infrastructure_status='in_progress',
    )
    session.add(building)
    await session.flush()

    muffle = Muffle(
        name='Муфта M-02',
        address_note='80м від будинку, колодязь №3',
        coordinate_lat=49.9935,
        coordinate_lon=36.2308,
    )
    session.add(muffle)
    await session.flush()

    fiber = Fiber(muffle_id=muffle.id, fiber_number=1, status=FiberStatus.reserved)
    session.add(fiber)
    await session.flush()

    panel = Panel(
        building_id=building.id,
        fiber_id=fiber.id,
        entrance_num=1,
        floor_num=1,
        label='П1-Щ1',
        installed_at=datetime.utcnow(),
    )
    session.add(panel)
    await session.flush()

    session.add(Port(panel_id=panel.id, port_number=1, status=PortStatus.free))
    session.add(Port(panel_id=panel.id, port_number=2, status=PortStatus.reserved))

    brigades = [
        Brigade(name='Б-1 Будівники', type=TaskType.construction),
        Brigade(name='З-1 Зварники', type=TaskType.welding),
        Brigade(name='П-1 Підключення', type=TaskType.connection),
    ]
    session.add_all(brigades)
    await session.flush()
    if brigades:
        brigades[0].foreman_id = builder.id
        brigades[1].foreman_id = welder.id
        brigades[2].foreman_id = connector.id

    tasks = [
        Task(
            type=TaskType.construction,
            status=TaskStatus.in_progress,
            priority=1,
            building_id=building.id,
            brigade_id=brigades[0].id,
            description='Кабельна траса: 80м ОКЛ-16, 4 під\'їзди, щитки на 5 поверхах',
            estimated_hours=4,
            assigned_at=datetime.utcnow() - timedelta(hours=2),
        ),
        Task(
            type=TaskType.welding,
            status=TaskStatus.pending,
            priority=1,
            building_id=building.id,
            brigade_id=brigades[1].id,
            description='Зварювання 8 муфт, під\'їзди 7–14',
            estimated_hours=6,
        ),
        Task(
            type=TaskType.connection,
            status=TaskStatus.assigned,
            priority=0,
            building_id=building.id,
            brigade_id=brigades[2].id,
            description='Підключення клієнта Іваненко О., порт 3А',
            estimated_hours=2,
        ),
    ]
    session.add_all(tasks)
    await session.flush()

    step_titles = [
        ('Отримати матеріали на складі', 'ОКЛ-16, муфти, патч-корди'),
        ('Прокласти кабель', 'Магістраль → під\'їзд 4'),
        ('Розвести в щитках', '12 щитків · кожні 5 поверхів'),
    ]
    for order, (title, hint) in enumerate(step_titles, start=1):
        session.add(TaskStep(task_id=tasks[0].id, step_order=order, title=title, hint=hint))

    stock = [
        StockItem(name='Кабель ОКЛ-16', unit='м', quantity=340, min_quantity=500),
        StockItem(name='Кабель ОКЛ-8', unit='м', quantity=220, min_quantity=200),
        StockItem(name='Муфта FOSC-16', unit='шт', quantity=8, min_quantity=5),
    ]
    session.add_all(stock)
    await session.flush()

    request = WarehouseRequest(
        requested_by=dispatcher.id,
        task_id=tasks[1].id,
        building_id=building.id,
        status=RequestStatus.pending,
        notes='Терміново потрібно 200м OКЛ-16 і щитки 5шт',
    )
    session.add(request)
    await session.flush()

    request_items = [
        WarehouseRequestItem(
            request_id=request.id,
            stock_item_id=stock[0].id,
            planned_qty=200,
        ),
        WarehouseRequestItem(
            request_id=request.id,
            stock_item_id=stock[2].id,
            planned_qty=5,
        ),
    ]
    session.add_all(request_items)
    await ensure_clean_tender_buildings(session)
    await session.commit()
