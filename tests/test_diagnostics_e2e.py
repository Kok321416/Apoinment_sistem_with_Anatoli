"""E2E: profile-scoped diagnostics (/s/{slug}/diagnostics/)."""
from __future__ import annotations

import re
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.auth.passwords import hash_password
from app.database import Base, get_async_db
from app.diagnostics.catalog import BAI, BHS, INTERPRETATION_LEAD_RU, get_test
from app.models import Calendar, Category, Consultant, Service, User


@pytest.fixture()
def diagnostics_client(tmp_path):
    from app.main import app

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _prepare(*, drop_diag_tables: bool = False):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            try:
                await conn.execute(text("ALTER TABLE consultants ADD COLUMN public_slug VARCHAR(64)"))
            except Exception:
                pass
            if drop_diag_tables:
                for table in (
                    "diagnostic_attempts",
                    "diagnostic_invitations",
                    "client_specialist_links",
                ):
                    try:
                        await conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
                    except Exception:
                        pass

        async with session_factory() as db:
            cat = Category(name_category="Общая")
            db.add(cat)
            await db.flush()
            spec_user = User(
                username="spec@test.com",
                email="spec@test.com",
                password=hash_password("specpass"),
                is_active=True,
                date_joined=datetime.utcnow(),
            )
            client_user = User(
                username="+79991234567",
                email="",
                password=hash_password("clientpass"),
                is_active=True,
                date_joined=datetime.utcnow(),
            )
            db.add(spec_user)
            db.add(client_user)
            await db.flush()
            consultant = Consultant(
                first_name="Артем",
                last_name="Тестов",
                email="spec@test.com",
                phone="+79990001122",
                category_of_specialist_id=cat.id,
                user_id=spec_user.id,
            )
            db.add(consultant)
            await db.flush()
            await db.execute(
                text("UPDATE consultants SET public_slug = :slug WHERE id = :id"),
                {"slug": "spec", "id": consultant.id},
            )
            cal = Calendar(
                consultant_id=consultant.id,
                name="Основной",
                color="#111111",
                is_active=True,
            )
            db.add(cal)
            await db.flush()
            db.add(
                Service(
                    consultant_id=consultant.id,
                    calendar_id=cal.id,
                    name="Консультация",
                    duration_minutes=60,
                    is_active=True,
                )
            )
            await db.commit()
            return consultant.id, client_user.id

    import asyncio

    consultant_id, client_user_id = asyncio.run(_prepare())

    async def override_get_async_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_async_db] = override_get_async_db

    import app.database as database_module

    database_module._async_engine = engine
    database_module._AsyncSessionLocal = session_factory

    client = TestClient(app)
    try:
        yield client, consultant_id, client_user_id, engine, session_factory, _prepare
    finally:
        app.dependency_overrides.clear()
        database_module._async_engine = None
        database_module._AsyncSessionLocal = None
        asyncio.run(engine.dispose())


def _login_client(client: TestClient, phone: str = "+79991234567", password: str = "clientpass"):
    r = client.get("/login/", follow_redirects=True)
    assert r.status_code == 200, r.text[:300]
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', r.text)
    assert m, "csrf_token missing on login page"
    csrf = m.group(1)
    return client.post(
        "/login/",
        data={"login": phone, "password": password, "csrf_token": csrf},
        follow_redirects=False,
    )


def _submit_bhs(client: TestClient, csrf: str) -> str:
    test = get_test(BHS.code)
    assert test and test.runnable
    data = {"csrf_token": csrf, "source": "profile"}
    for item in test.items:
        data[item.id] = str(item.options[0][1])
    submit = client.post(
        f"/s/spec/diagnostics/tests/{BHS.code}/submit/",
        data=data,
        follow_redirects=False,
    )
    assert submit.status_code == 302, submit.text[:500]
    loc = submit.headers.get("location") or ""
    assert "/s/spec/diagnostics/results/" in loc, f"unexpected redirect: {loc}"
    return loc


def _submit_bai(client: TestClient, csrf: str, *, score_value: int = 1) -> str:
    test = get_test(BAI.code)
    assert test and test.runnable
    data = {"csrf_token": csrf, "source": "profile"}
    for item in test.items:
        data[item.id] = str(score_value)
    submit = client.post(
        f"/s/spec/diagnostics/tests/{BAI.code}/submit/",
        data=data,
        follow_redirects=False,
    )
    assert submit.status_code == 302, submit.text[:500]
    loc = submit.headers.get("location") or ""
    assert "/s/spec/diagnostics/results/" in loc, f"unexpected redirect: {loc}"
    return loc


def test_diagnostics_requires_login(diagnostics_client):
    client, _cid, _uid, *_ = diagnostics_client
    r = client.get("/s/spec/diagnostics/", follow_redirects=False)
    assert r.status_code == 302
    assert "/s/spec/welcome/" in (r.headers.get("location") or "")


def test_diagnostics_welcome_page_mentions_diagnostics(diagnostics_client):
    client, _cid, _uid, *_ = diagnostics_client
    r = client.get(
        "/s/spec/welcome/?next=/s/spec/diagnostics/",
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "диагностик" in r.text.lower()


def test_profile_shows_diagnostics_link(diagnostics_client):
    client, _cid, _uid, *_ = diagnostics_client
    r = client.get("/s/spec/", follow_redirects=True)
    assert r.status_code == 200
    assert "Перейти к диагностике" in r.text
    assert "/s/spec/diagnostics/" in r.text


def test_logged_out_with_booking_gate_still_requires_account(diagnostics_client):
    """After logout, booking gate alone must not open diagnostics (needs user account)."""
    client, _cid, _uid, *_ = diagnostics_client
    _login_client(client)
    client.get("/s/spec/", follow_redirects=True)
    client.get("/s/spec/diagnostics/", follow_redirects=True)

    take = client.get(f"/s/spec/diagnostics/tests/{BHS.code}/run/", follow_redirects=True)
    csrf_m = re.search(r'name="csrf_token"\s+value="([^"]+)"', take.text)
    assert csrf_m, "csrf for logout"
    client.post("/logout/", data={"csrf_token": csrf_m.group(1)}, follow_redirects=True)

    r = client.get("/s/spec/diagnostics/", follow_redirects=False)
    assert r.status_code == 302
    assert "/s/spec/welcome/" in (r.headers.get("location") or "")


def test_diagnostics_hub_and_submit_bhs(diagnostics_client):
    client, _cid, _uid, *_ = diagnostics_client
    login_r = _login_client(client)
    assert login_r.status_code == 302, login_r.text[:300]

    hub = client.get("/s/spec/diagnostics/", follow_redirects=True)
    assert hub.status_code == 200, hub.text[:500]
    assert "Диагностика" in hub.text
    assert BHS.title in hub.text

    take = client.get(f"/s/spec/diagnostics/tests/{BHS.code}/run/", follow_redirects=True)
    assert take.status_code == 200, take.text[:500]
    assert "Вопрос" in take.text

    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', take.text)
    assert m, "csrf_token missing on take page"
    loc = _submit_bhs(client, m.group(1))

    result = client.get(loc, follow_redirects=True)
    assert result.status_code == 200, result.text[:500]
    assert "Безнадёжность" in result.text or "безнад" in result.text.lower()

    hub2 = client.get("/s/spec/diagnostics/", follow_redirects=True)
    assert hub2.status_code == 200
    assert "История результатов" in hub2.text
    assert "Полная расшифровка" in hub2.text or BHS.title in hub2.text


def test_diagnostics_hub_and_submit_bai_with_interpretation(diagnostics_client):
    """BAI from psytests depT1u: hub → take → submit → client+specialist see interpretation lead."""
    import asyncio

    from sqlalchemy import select

    from app.models import ClientCard, DiagnosticAttempt

    client, consultant_id, client_user_id, _engine, session_factory, _prepare = diagnostics_client
    _login_client(client)

    hub = client.get("/s/spec/diagnostics/", follow_redirects=True)
    assert hub.status_code == 200
    assert BAI.title in hub.text
    assert f"/s/spec/diagnostics/tests/{BAI.code}/" in hub.text

    take = client.get(f"/s/spec/diagnostics/tests/{BAI.code}/run/", follow_redirects=True)
    assert take.status_code == 200, take.text[:500]
    assert "Вопрос" in take.text
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', take.text)
    assert m, "csrf_token missing on BAI take page"
    loc = _submit_bai(client, m.group(1), score_value=1)

    result = client.get(loc, follow_redirects=True)
    assert result.status_code == 200, result.text[:500]
    assert "Тревога" in result.text or "тревог" in result.text.lower()
    assert INTERPRETATION_LEAD_RU[:40] in result.text
    assert "предположительный" in result.text.lower() or "психологом" in result.text.lower()
    assert "умеренн" in result.text.lower()  # 21 items × 1 = 21 → moderate

    async def _card_and_attempt():
        async with session_factory() as db:
            card = (
                await db.execute(
                    select(ClientCard).where(
                        ClientCard.consultant_id == consultant_id,
                        ClientCard.client_user_id == client_user_id,
                    )
                )
            ).scalar_one_or_none()
            attempt = (
                await db.execute(
                    select(DiagnosticAttempt).where(
                        DiagnosticAttempt.client_user_id == client_user_id,
                        DiagnosticAttempt.test_code == BAI.code,
                    )
                )
            ).scalar_one_or_none()
            return card, attempt

    card, attempt = asyncio.run(_card_and_attempt())
    assert card is not None
    assert attempt is not None and attempt.status == "completed"

    spec = TestClient(client.app)
    login_page = spec.get("/login/", follow_redirects=True)
    csrf_m = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_page.text)
    assert csrf_m
    spec.post(
        "/login/",
        data={"login": "spec@test.com", "password": "specpass", "csrf_token": csrf_m.group(1)},
        follow_redirects=False,
    )
    crm = spec.get(f"/clients/{card.id}/#diagnostics", follow_redirects=True)
    assert crm.status_code == 200
    assert BAI.title in crm.text or "Тревога" in crm.text
    assert INTERPRETATION_LEAD_RU[:40] in crm.text

    detail = spec.get(f"/diagnostics/results/{attempt.id}/", follow_redirects=False)
    assert detail.status_code == 200, detail.headers.get("location")
    assert INTERPRETATION_LEAD_RU[:40] in detail.text
    assert "Интерпретация" in detail.text


def _submit_client_status(client: TestClient, csrf: str, **overrides) -> str:
    data = {
        "csrf_token": csrf,
        "source": "profile",
        "i1": "married",
        "i2": "partner",
        "i3": "7",
        "i4": "anxiety",
        "i5": "months",
        "i6": "talk",
        "i7": "one",
        "i8": "rather_good",
        "i9": "work",
        "i9b": "6",
        "i10": "rather_calm",
        "i11": "rather_safe",
        "i12": "close",
        "i13": "no",
        "i14": "no",
        "i16": "anxiety",
    }
    data.update(overrides)
    submit = client.post(
        "/s/spec/diagnostics/tests/client_status/submit/",
        data=data,
        follow_redirects=False,
    )
    assert submit.status_code == 302, submit.text[:800]
    loc = submit.headers.get("location") or ""
    assert "/s/spec/diagnostics/results/" in loc, f"unexpected redirect: {loc}"
    return loc


def test_diagnostics_hub_features_client_status_and_saves_answers(diagnostics_client):
    import asyncio

    from sqlalchemy import select

    from app.models import ClientCard, DiagnosticAttempt

    client, consultant_id, client_user_id, _engine, session_factory, _prepare = diagnostics_client
    _login_client(client)

    hub = client.get("/s/spec/diagnostics/", follow_redirects=True)
    assert hub.status_code == 200
    assert "diag-card--featured" in hub.text
    assert "Общий опрос по статусу" in hub.text
    assert hub.text.find("Общий опрос по статусу") < hub.text.find(BHS.title)
    assert "type=\"range\"" not in hub.text

    take = client.get("/s/spec/diagnostics/tests/client_status/run/", follow_redirects=True)
    assert take.status_code == 200, take.text[:500]
    assert 'type="range"' in take.text
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', take.text)
    assert m
    loc = _submit_client_status(client, m.group(1), i13="yes", i13_note="")

    result = client.get(loc, follow_redirects=True)
    assert result.status_code == 200, result.text[:500]
    assert INTERPRETATION_LEAD_RU[:40] in result.text
    assert "Как вы оцениваете своё состояние" in result.text
    assert "Тревога" in result.text

    async def _attempt():
        async with session_factory() as db:
            card = (
                await db.execute(
                    select(ClientCard).where(
                        ClientCard.consultant_id == consultant_id,
                        ClientCard.client_user_id == client_user_id,
                    )
                )
            ).scalar_one_or_none()
            attempt = (
                await db.execute(
                    select(DiagnosticAttempt).where(
                        DiagnosticAttempt.client_user_id == client_user_id,
                        DiagnosticAttempt.test_code == "client_status",
                    )
                )
            ).scalar_one_or_none()
            return card, attempt

    card, attempt = asyncio.run(_attempt())
    assert card is not None
    assert attempt is not None and attempt.status == "completed"
    assert attempt.answers_json and attempt.answers_json != "{}"
    assert '"i3"' in attempt.answers_json

    with TestClient(client.app) as spec:
        login_page = spec.get("/login/", follow_redirects=True)
        csrf_m = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_page.text)
        assert csrf_m
        spec.post(
            "/login/",
            data={"login": "spec@test.com", "password": "specpass", "csrf_token": csrf_m.group(1)},
            follow_redirects=False,
        )
        crm = spec.get(f"/clients/{card.id}/#diagnostics", follow_redirects=True)
        assert crm.status_code == 200
        assert "Общий опрос по статусу" in crm.text
        assert "Тревога" in crm.text or "состояние" in crm.text.lower()


def test_diagnostics_flow_from_profile_link(diagnostics_client):
    client, _cid, _uid, *_ = diagnostics_client
    _login_client(client)
    profile = client.get("/s/spec/", follow_redirects=True)
    assert profile.status_code == 200
    m = re.search(r'href="(/s/spec/diagnostics/)"', profile.text)
    assert m, "diagnostics link missing on profile"
    hub = client.get(m.group(1), follow_redirects=True)
    assert hub.status_code == 200
    assert BHS.title in hub.text


def test_diagnostics_works_when_tables_missing_initially(diagnostics_client):
    import asyncio

    from app.services.diagnostics_service import reset_diagnostics_ddl_ready_for_tests

    reset_diagnostics_ddl_ready_for_tests()
    client, _cid, _uid, engine, session_factory, prepare = diagnostics_client
    asyncio.run(engine.dispose())

    from app.main import app

    asyncio.run(prepare(drop_diag_tables=True))

    async def override_get_async_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_async_db] = override_get_async_db

    from unittest.mock import patch

    with patch("app.db_schema.ensure_diagnostics_schema", return_value=False):
        reset_diagnostics_ddl_ready_for_tests()
        client = TestClient(app)
        _login_client(client)
        take = client.get(f"/s/spec/diagnostics/tests/{BHS.code}/run/", follow_redirects=True)
        assert take.status_code == 200, take.text[:400]
        m = re.search(r'name="csrf_token"\s+value="([^"]+)"', take.text)
        assert m
        loc = _submit_bhs(client, m.group(1))
        result = client.get(loc, follow_redirects=True)
        assert result.status_code == 200, result.text[:400]


def test_diagnostics_result_idor_redirects_other_client(diagnostics_client):
    """Client B must not read client A diagnostic attempt."""
    client, _cid, client_a_id, engine, session_factory, _prepare = diagnostics_client
    _login_client(client)
    take = client.get(f"/s/spec/diagnostics/tests/{BHS.code}/run/", follow_redirects=True)
    assert take.status_code == 200
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', take.text)
    assert m
    loc = _submit_bhs(client, m.group(1))
    attempt_id = int(re.search(r"/results/(\d+)/", loc).group(1))

    import asyncio
    from datetime import datetime

    from sqlalchemy import select

    from app.auth.passwords import hash_password
    from app.models import User

    async def _add_client_b():
        async with session_factory() as db:
            user_b = User(
                username="+79997654321",
                email="",
                password=hash_password("clientpass2"),
                is_active=True,
                date_joined=datetime.utcnow(),
            )
            db.add(user_b)
            await db.commit()
            return user_b.id

    client_b_id = asyncio.run(_add_client_b())
    assert client_b_id != client_a_id

    client_b = TestClient(client.app)
    login_page = client_b.get("/login/", follow_redirects=True)
    csrf_m = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_page.text)
    assert csrf_m
    client_b.post(
        "/login/",
        data={"login": "+79997654321", "password": "clientpass2", "csrf_token": csrf_m.group(1)},
        follow_redirects=False,
    )

    denied = client_b.get(f"/s/spec/diagnostics/results/{attempt_id}/", follow_redirects=False)
    assert denied.status_code == 302
    assert "/s/spec/diagnostics/" in (denied.headers.get("location") or "")


def test_diagnostics_creates_client_card_and_specialist_sees_results(diagnostics_client):
    import asyncio

    from sqlalchemy import select

    from app.models import ClientCard, DiagnosticAttempt

    client, consultant_id, client_user_id, _engine, session_factory, _prepare = diagnostics_client
    _login_client(client)
    take = client.get(f"/s/spec/diagnostics/tests/{BHS.code}/run/", follow_redirects=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', take.text)
    assert m
    loc = _submit_bhs(client, m.group(1))
    assert "/results/preview/" not in loc

    async def _fetch_card_and_attempt():
        async with session_factory() as db:
            card = (
                await db.execute(
                    select(ClientCard).where(
                        ClientCard.consultant_id == consultant_id,
                        ClientCard.client_user_id == client_user_id,
                    )
                )
            ).scalar_one_or_none()
            attempt = (
                await db.execute(
                    select(DiagnosticAttempt).where(DiagnosticAttempt.client_user_id == client_user_id)
                )
            ).scalar_one_or_none()
            return card, attempt

    card, attempt = asyncio.run(_fetch_card_and_attempt())
    assert card is not None
    assert attempt is not None
    assert attempt.status == "completed"
    assert attempt.client_card_id == card.id

    async def _list_for_card():
        from app.services.diagnostics_service import attempt_to_view, list_attempts_for_card

        async with session_factory() as db:
            rows = await list_attempts_for_card(
                db, consultant_id=consultant_id, client_card_id=card.id
            )
            return [attempt_to_view(r) for r in rows]

    views = asyncio.run(_list_for_card())
    assert views
    assert views[0]["test_code"] == BHS.code

    # Specialist CRM card page must render (no Internal Server Error) with results.
    spec = TestClient(client.app)
    login_page = spec.get("/login/", follow_redirects=True)
    csrf_m = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_page.text)
    assert csrf_m
    spec.post(
        "/login/",
        data={"login": "spec@test.com", "password": "specpass", "csrf_token": csrf_m.group(1)},
        follow_redirects=False,
    )
    page = spec.get(f"/clients/{card.id}/#diagnostics", follow_redirects=True)
    assert page.status_code == 200, page.text[:800]
    assert "Диагностика" in page.text
    assert "Internal Server Error" not in page.text
    assert views[0]["title"] in page.text or BHS.code in page.text

    # Specialist opens client results from CRM (different accounts).
    detail = spec.get(f"/diagnostics/results/{attempt.id}/", follow_redirects=False)
    assert detail.status_code == 200, (
        f"expected 200 results page, got {detail.status_code} loc={detail.headers.get('location')}"
    )
    assert "результат" in detail.text.lower() or views[0]["title"] in detail.text
    assert "Internal Server Error" not in detail.text

    # Hash tab on card must stay on the same card URL (not redirect to list).
    tab = spec.get(f"/clients/{card.id}/#diagnostics", follow_redirects=False)
    assert tab.status_code == 200
    assert "Диагностика" in tab.text


def test_dual_role_specialist_opens_own_results_from_crm(diagnostics_client):
    """Same account is specialist + client: CRM → results must not bounce to /clients/ list."""
    import asyncio

    from sqlalchemy import select

    from app.models import ClientCard, DiagnosticAttempt

    client, consultant_id, _client_user_id, _engine, session_factory, _prepare = diagnostics_client

    # Log in as specialist and take the test as that same user (Artem dual-role).
    login_page = client.get("/login/", follow_redirects=True)
    csrf_m = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_page.text)
    assert csrf_m
    client.post(
        "/login/",
        data={"login": "spec@test.com", "password": "specpass", "csrf_token": csrf_m.group(1)},
        follow_redirects=False,
    )
    take = client.get(f"/s/spec/diagnostics/tests/{BHS.code}/run/", follow_redirects=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', take.text)
    assert m
    loc = _submit_bhs(client, m.group(1))
    attempt_id = int(loc.rstrip("/").split("/")[-1])

    async def _card_for_spec():
        async with session_factory() as db:
            attempt = await db.get(DiagnosticAttempt, attempt_id)
            card = (
                await db.execute(
                    select(ClientCard).where(
                        ClientCard.consultant_id == consultant_id,
                        ClientCard.client_user_id == attempt.client_user_id,
                    )
                )
            ).scalar_one_or_none()
            return attempt.client_user_id, card.id if card else None, attempt.client_card_id

    user_id, card_id, linked = asyncio.run(_card_for_spec())
    assert linked or card_id
    card_id = linked or card_id

    crm = client.get(f"/clients/{card_id}/#diagnostics", follow_redirects=True)
    assert crm.status_code == 200, crm.text[:500]
    assert "clients/?error" not in str(crm.url)
    assert "Диагностика" in crm.text

    # Critical: must render results in cabinet, not redirect to public hub or list.
    results = client.get(f"/diagnostics/results/{attempt_id}/", follow_redirects=False)
    assert results.status_code == 200, (
        f"got {results.status_code} location={results.headers.get('location')}"
    )
    assert "К диагностике" in results.text
    assert f"/clients/{card_id}/#diagnostics" in results.text


def test_specialist_results_for_email_client_like_artem(diagnostics_client):
    """CRM diagnostics → results for client email kok321416x@yandex.ru."""
    import asyncio

    from sqlalchemy import select

    from app.models import ClientCard, DiagnosticAttempt, User

    client, consultant_id, client_user_id, _engine, session_factory, _prepare = diagnostics_client

    async def _set_email():
        async with session_factory() as db:
            user = await db.get(User, client_user_id)
            user.email = "kok321416x@yandex.ru"
            await db.commit()

    asyncio.run(_set_email())
    _login_client(client)
    take = client.get(f"/s/spec/diagnostics/tests/{BHS.code}/run/", follow_redirects=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', take.text)
    assert m
    loc = _submit_bhs(client, m.group(1))
    attempt_id = int(loc.rstrip("/").split("/")[-1])

    async def _card_id():
        async with session_factory() as db:
            card = (
                await db.execute(
                    select(ClientCard).where(
                        ClientCard.consultant_id == consultant_id,
                        ClientCard.client_user_id == client_user_id,
                    )
                )
            ).scalar_one()
            return card.id

    card_id = asyncio.run(_card_id())

    spec = TestClient(client.app)
    login_page = spec.get("/login/", follow_redirects=True)
    csrf_m = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_page.text)
    assert csrf_m
    spec.post(
        "/login/",
        data={"login": "spec@test.com", "password": "specpass", "csrf_token": csrf_m.group(1)},
        follow_redirects=False,
    )

    crm = spec.get(f"/clients/{card_id}/#diagnostics", follow_redirects=True)
    assert crm.status_code == 200
    assert "panel-diagnostics" in crm.text or "Диагностика" in crm.text

    results = spec.get(f"/diagnostics/results/{attempt_id}/", follow_redirects=True)
    assert results.status_code == 200
    assert "Internal Server Error" not in results.text
    assert f"/clients/{card_id}/#diagnostics" in results.text or "К диагностике" in results.text
    # Must not land on the clients list as the primary page
    assert 'id="clients-page"' not in results.text and "client-cards" not in results.text.lower()


def test_list_attempts_for_card_matches_by_email_when_user_id_unlinked(diagnostics_client):
    import asyncio

    from sqlalchemy import select

    from app.models import ClientCard, DiagnosticAttempt, User
    from app.services.diagnostics_service import list_attempts_for_card

    client, consultant_id, client_user_id, _engine, session_factory, _prepare = diagnostics_client
    _login_client(client)
    take = client.get(f"/s/spec/diagnostics/tests/{BHS.code}/run/", follow_redirects=True)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', take.text)
    assert m
    _submit_bhs(client, m.group(1))

    async def _unlink_and_list():
        async with session_factory() as db:
            user = await db.get(User, client_user_id)
            user.email = "kok321416x@yandex.ru"
            card = (
                await db.execute(
                    select(ClientCard).where(
                        ClientCard.consultant_id == consultant_id,
                        ClientCard.client_user_id == client_user_id,
                    )
                )
            ).scalar_one()
            # Simulate CRM card created from email without user link; attempt keeps user id.
            card.client_user_id = None
            card.email = "kok321416x@yandex.ru"
            attempt = (
                await db.execute(
                    select(DiagnosticAttempt).where(DiagnosticAttempt.client_user_id == client_user_id)
                )
            ).scalar_one()
            attempt.client_card_id = None
            await db.commit()
            card_id = card.id
            rows = await list_attempts_for_card(
                db, consultant_id=consultant_id, client_card_id=card_id
            )
            return card_id, [r.id for r in rows], rows[0].client_card_id if rows else None

    card_id, ids, linked = asyncio.run(_unlink_and_list())
    assert ids
    assert linked == card_id


def test_client_card_detail_survives_diagnostics_session_rollback(diagnostics_client):
    """Regression: diagnostics DB error must not leave expired card → 500."""
    import asyncio
    from unittest.mock import AsyncMock, patch

    from sqlalchemy import select

    from app.models import ClientCard

    client, consultant_id, client_user_id, _engine, session_factory, _prepare = diagnostics_client

    async def _card_id():
        async with session_factory() as db:
            card = ClientCard(
                consultant_id=consultant_id,
                client_user_id=client_user_id,
                name="Client",
                email="client@test.com",
            )
            db.add(card)
            await db.commit()
            await db.refresh(card)
            return card.id

    card_id = asyncio.run(_card_id())
    spec = TestClient(client.app)
    login_page = spec.get("/login/", follow_redirects=True)
    csrf_m = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_page.text)
    assert csrf_m
    spec.post(
        "/login/",
        data={"login": "spec@test.com", "password": "specpass", "csrf_token": csrf_m.group(1)},
        follow_redirects=False,
    )

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated diagnostics failure")

    with patch(
        "app.services.diagnostics_service.list_attempts_for_card",
        new=AsyncMock(side_effect=_boom),
    ):
        page = spec.get(f"/clients/{card_id}/", follow_redirects=True)
    assert page.status_code == 200, page.text[:800]
    assert "Internal Server Error" not in page.text
    assert "Клиент" in page.text or "client" in page.text.lower() or "Client" in page.text
