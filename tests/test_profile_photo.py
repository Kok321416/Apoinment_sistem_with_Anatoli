"""Profile photo upload tests."""
from io import BytesIO

import pytest
from PIL import Image
from starlette.datastructures import UploadFile


def _jpeg_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (64, 64), "red").save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.anyio
async def test_save_profile_photo_from_upload(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.models  # noqa: F401
    from app.database import Base
    from app.models import Category, Consultant, User
    from app.routers import pages as pages_router

    monkeypatch.setattr(pages_router, "settings", type("S", (), {"media_root": tmp_path})())

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    category = Category(name_category="Общая")
    db.add(category)
    db.flush()
    user = User(username="u1", email="u1@test.com", password="x", is_active=True)
    db.add(user)
    db.flush()
    consultant = Consultant(
        user_id=user.id,
        first_name="A",
        last_name="B",
        email="u1@test.com",
        phone="+79990000000",
        category_of_specialist_id=category.id,
    )
    db.add(consultant)
    db.flush()

    upload = UploadFile(file=BytesIO(_jpeg_bytes()), filename="photo.jpg")
    err = await pages_router._save_profile_photo(consultant, upload)
    assert err is None
    assert consultant.profile_photo == f"consultants/{consultant.id}/photo.jpg"
    assert (tmp_path / consultant.profile_photo).is_file()
    db.close()


@pytest.mark.anyio
async def test_read_upload_bytes_after_async_read():
    from app.routers.pages import _read_upload_bytes

    raw = _jpeg_bytes()
    upload = UploadFile(file=BytesIO(raw), filename="photo.jpg")
    await upload.read()
    data = await _read_upload_bytes(upload, 1024 * 1024)
    assert len(data) == len(raw)
