"""Billing plans and subscriptions (Admin A5+, provider integration later)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import BillingPlan, UserSubscription

SUB_ACTIVE = "active"
SUB_CANCELLED = "cancelled"
SUB_TRIAL = "trial"


def list_billing_plans(db: Session, *, active_only: bool = False) -> list[BillingPlan]:
    q = db.query(BillingPlan).order_by(BillingPlan.sort_order.asc(), BillingPlan.id.asc())
    if active_only:
        q = q.filter(BillingPlan.is_active.is_(True))
    return q.all()


def create_billing_plan(
    db: Session,
    *,
    code: str,
    name: str,
    price_rub: int,
    interval: str = "month",
) -> tuple[BillingPlan | None, str | None]:
    code = (code or "").strip().lower()
    name = (name or "").strip()
    interval = (interval or "month").strip().lower()
    if not code or not name:
        return None, "Укажите code и название"
    if price_rub < 0:
        return None, "Цена не может быть отрицательной"
    if interval not in ("month", "year"):
        return None, "interval: month или year"
    if db.query(BillingPlan).filter(BillingPlan.code == code).first():
        return None, "Тариф с таким code уже есть"
    plan = BillingPlan(
        code=code,
        name=name,
        price_rub=int(price_rub),
        interval=interval,
        is_active=True,
        sort_order=0,
        created_at=datetime.utcnow(),
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan, None


def toggle_plan_active(db: Session, plan_id: int) -> tuple[BillingPlan | None, str | None]:
    plan = db.get(BillingPlan, plan_id)
    if not plan:
        return None, "Тариф не найден"
    plan.is_active = not bool(plan.is_active)
    db.commit()
    db.refresh(plan)
    return plan, None


def billing_snapshot(db: Session) -> dict[str, Any]:
    plans_total = db.query(func.count(BillingPlan.id)).scalar() or 0
    active_plans = (
        db.query(func.count(BillingPlan.id)).filter(BillingPlan.is_active.is_(True)).scalar() or 0
    )
    active_subs = (
        db.query(func.count(UserSubscription.id))
        .filter(UserSubscription.status == SUB_ACTIVE)
        .scalar()
        or 0
    )
    mrr = 0
    rows = (
        db.query(BillingPlan.price_rub, func.count(UserSubscription.id))
        .join(UserSubscription, UserSubscription.plan_id == BillingPlan.id)
        .filter(UserSubscription.status == SUB_ACTIVE, BillingPlan.interval == "month")
        .group_by(BillingPlan.id, BillingPlan.price_rub)
        .all()
    )
    for price, cnt in rows:
        mrr += int(price or 0) * int(cnt or 0)
    return {
        "enabled": active_plans > 0,
        "provider": None,
        "plans_total": int(plans_total),
        "active_plans": int(active_plans),
        "active_subscriptions": int(active_subs),
        "mrr_rub": mrr,
        "message": "Провайдер оплаты не подключён. Тарифы можно завести вручную для учёта.",
    }
