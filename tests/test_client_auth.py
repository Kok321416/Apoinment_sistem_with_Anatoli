"""Client phone login helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.client_auth import (
    find_user_by_login_async,
    login_identifier_to_username,
    resolve_client_user_id_by_phone_async,
)


def test_login_identifier_phone():
    assert login_identifier_to_username("+7 (999) 123-45-67") == "+79991234567"


def test_login_identifier_email():
    assert login_identifier_to_username("User@Example.com") == "user@example.com"


@pytest.mark.asyncio
async def test_find_user_by_login_phone():
    user = MagicMock(id=5)
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    found = await find_user_by_login_async(db, "89991234567")
    assert found is user


@pytest.mark.asyncio
async def test_resolve_client_user_id_skips_specialist():
    user = MagicMock(id=3)
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    consultant_result = MagicMock()
    consultant_result.first.return_value = (1,)
    db = AsyncMock()

    async def execute(stmt):
        sql = str(stmt)
        if "consultants" in sql.lower():
            return consultant_result
        return user_result

    db.execute = execute
    assert await resolve_client_user_id_by_phone_async(db, "+79991234567") is None


@pytest.mark.asyncio
async def test_resolve_client_user_id_for_client():
    user = MagicMock(id=7)
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    consultant_result = MagicMock()
    consultant_result.first.return_value = None
    db = AsyncMock()

    async def execute(stmt):
        sql = str(stmt)
        if "consultants" in sql.lower():
            return consultant_result
        return user_result

    db.execute = execute
    assert await resolve_client_user_id_by_phone_async(db, "+79991234567") == 7
