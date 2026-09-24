"""Rider wallet balances, transactions and withdrawals."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.delivery import Delivery
from app.models.enums import DeliveryStatus, PayoutStatus
from app.models.order import Order
from app.models.rider_wallet import RiderWallet
from app.models.user import RiderProfile, User
from app.models.wallet_transaction import WalletTransaction

IMPS_FEE_CENTS = 500
FILTER_MAP = {
    "all": None,
    "withdrawals": "withdrawal",
    "earnings": "order_earning",
    "incentives": "incentive",
}


def _get_or_create_wallet(db: Session, rider_id: int) -> RiderWallet:
    wallet = db.execute(
        select(RiderWallet).where(RiderWallet.rider_id == rider_id)
    ).scalar_one_or_none()
    if wallet is None:
        wallet = RiderWallet(rider_id=rider_id)
        db.add(wallet)
        db.flush()
    return wallet


def _recalculate_available(db: Session, wallet: RiderWallet) -> None:
    wallet.available_balance_cents = max(
        0, wallet.total_balance_cents - wallet.locked_balance_cents
    )


def _time_label(dt: datetime) -> str:
    now = utcnow()
    if dt.date() == now.date():
        prefix = "Today"
    elif dt.date() == (now - timedelta(days=1)).date():
        prefix = "Yesterday"
    else:
        prefix = dt.strftime("%b %d")
    return f"{prefix}, {dt.strftime('%I:%M %p').lstrip('0')}"


def _build_payout_accounts(profile: RiderProfile | None, user: User | None) -> list[dict]:
    bank_name = profile.bank_name if profile else "HDFC Bank"
    bank_masked = profile.bank_account_masked if profile else "8839"
    holder = user.full_name if user else "Partner"
    accounts = [
        {
            "id": "bank_primary",
            "type": "bank",
            "label": bank_name,
            "account_masked": bank_masked,
            "holder_name": holder,
            "verified": True,
            "is_primary": True,
            "eta_label": "15–30 mins via IMPS",
            "icon": "business",
        },
    ]
    if profile and profile.upi_linked:
        accounts.append({
            "id": "upi_primary",
            "type": "upi",
            "label": "UPI Instant",
            "account_masked": "rahul.sharma@okhdfc",
            "holder_name": holder,
            "verified": True,
            "is_primary": False,
            "eta_label": "Instant (under 2 mins)",
            "icon": "flash",
        })
    return accounts


def _account_destination_label(account: dict) -> str:
    if account["type"] == "upi":
        return f"UPI • {account['account_masked']}"
    return f"Bank IMPS • {account['label']} (•••• {account['account_masked']})"


def _txn_icon(txn_type: str) -> str:
    return {
        "withdrawal": "arrow-up-circle",
        "order_earning": "fast-food",
        "incentive": "star",
        "weekly_payout": "calendar",
    }.get(txn_type, "receipt")


def build_wallet(db: Session, rider_id: int) -> dict:
    wallet = _get_or_create_wallet(db, rider_id)
    # Credit delivered-order earnings into the ledger before reading balances so
    # every caller reflects real earnings. Idempotent (keyed by ORD-<id>).
    # Previously only the rider endpoint synced, so the admin partner view and
    # withdrawals showed a stale ₹0 balance despite completed deliveries.
    sync_from_deliveries(db, rider_id)
    profile = db.execute(
        select(RiderProfile).where(RiderProfile.user_id == rider_id)
    ).scalar_one_or_none()
    user = db.get(User, rider_id)
    payout_accounts = _build_payout_accounts(profile, user)
    _recalculate_available(db, wallet)

    processing = db.execute(
        select(WalletTransaction)
        .where(
            WalletTransaction.rider_id == rider_id,
            WalletTransaction.txn_type == "withdrawal",
            WalletTransaction.status == "processing",
        )
        .order_by(WalletTransaction.created_at.desc())
    ).scalars().first()

    bank_name = profile.bank_name if profile else "HDFC Bank"
    bank_masked = profile.bank_account_masked if profile else "4821"

    return {
        "total_balance_cents": wallet.total_balance_cents,
        "locked_balance_cents": wallet.locked_balance_cents,
        "available_balance_cents": wallet.available_balance_cents,
        "instant_payout_active": True,
        "updated_label": "Updated just now",
        "bank": {
            "bank_name": bank_name,
            "account_masked": bank_masked,
            "verified": bool(profile and profile.upi_linked),
            "label": "Primary IMPS / UPI destination",
        },
        "processing_withdrawal": {
            "amount_cents": abs(processing.amount_cents) if processing else 0,
            "reference_number": processing.reference_number if processing else "",
            "bank_label": f"Bank IMPS • {bank_name} (•••• {bank_masked})",
            "eta_label": "Expected within 15–30 mins",
            "status": processing.status if processing else None,
        } if processing else None,
        "quick_amounts_cents": [50000, 100000, 200000],
        "cashout_fee_cents": IMPS_FEE_CENTS,
        "payout_accounts": payout_accounts,
        "min_withdraw_cents": IMPS_FEE_CENTS + 100,
    }


def list_transactions(db: Session, rider_id: int, filter: str = "all") -> dict:
    q = select(WalletTransaction).where(WalletTransaction.rider_id == rider_id)
    txn_type = FILTER_MAP.get(filter)
    if txn_type:
        if txn_type == "withdrawal":
            q = q.where(WalletTransaction.txn_type.in_(["withdrawal", "weekly_payout"]))
        else:
            q = q.where(WalletTransaction.txn_type == txn_type)
    rows = db.execute(q.order_by(WalletTransaction.created_at.desc())).scalars().all()
    items = []
    for t in rows:
        items.append({
            "id": t.id,
            "txn_type": t.txn_type,
            "icon": _txn_icon(t.txn_type),
            "title": t.title,
            "subtitle": t.subtitle,
            "amount_cents": t.amount_cents,
            "status": t.status,
            "status_label": t.status.upper(),
            "reference_number": t.reference_number,
            "time_label": _time_label(t.created_at),
            "order_id": t.order_id,
        })
    return {"filter": filter, "count": len(items), "items": items}


def withdraw(db: Session, rider_id: int, amount_cents: int, account_id: str = "bank_primary") -> dict:
    if amount_cents <= IMPS_FEE_CENTS:
        raise HTTPException(status_code=400, detail="Amount must exceed the IMPS fee")
    wallet = _get_or_create_wallet(db, rider_id)
    _recalculate_available(db, wallet)
    if amount_cents > wallet.available_balance_cents:
        raise HTTPException(status_code=400, detail="Insufficient available balance")
    profile = db.execute(
        select(RiderProfile).where(RiderProfile.user_id == rider_id)
    ).scalar_one_or_none()
    user = db.get(User, rider_id)
    accounts = _build_payout_accounts(profile, user)
    account = next((a for a in accounts if a["id"] == account_id), accounts[0])
    dest = _account_destination_label(account)
    ref = f"WD-{89214 + len(db.execute(select(WalletTransaction)).scalars().all())}"
    from app.services.withdrawal_admin_service import _risk_for_rider
    risk_score, risk_label = _risk_for_rider(db, profile, user, amount_cents)
    txn = WalletTransaction(
        rider_id=rider_id,
        txn_type="withdrawal",
        amount_cents=-amount_cents,
        status="processing",
        reference_number=ref,
        title="Instant Withdrawal",
        subtitle=f"{dest} • Today, {utcnow().strftime('%I:%M %p').lstrip('0')}",
        fee_cents=IMPS_FEE_CENTS,
        risk_score=risk_score,
        risk_label=risk_label,
        payout_cycle=f"Payout Cycle #{48 + (len(ref) % 6)}",
    )
    db.add(txn)
    wallet.total_balance_cents = max(0, wallet.total_balance_cents - amount_cents)
    _recalculate_available(db, wallet)
    db.flush()
    return {
        "ok": True,
        "amount_cents": amount_cents - IMPS_FEE_CENTS,
        "fee_cents": IMPS_FEE_CENTS,
        "reference_number": ref,
        "message": f"₹{(amount_cents - IMPS_FEE_CENTS) / 100:.2f} withdrawal is processing",
        "eta_label": account["eta_label"],
    }


def sync_from_deliveries(db: Session, rider_id: int) -> None:
    """Ensure order earnings appear in wallet ledger."""
    wallet = _get_or_create_wallet(db, rider_id)
    deliveries = db.execute(
        select(Delivery)
        .join(Order, Delivery.order_id == Order.id)
        .where(
            Delivery.rider_id == rider_id,
            Delivery.status == DeliveryStatus.delivered,
        )
    ).scalars().all()
    locked = 0
    for d in deliveries:
        order = db.get(Order, d.order_id)
        if order and order.payment_method == "cod" and d.payout_status == PayoutStatus.pending:
            locked += d.earning_cents + d.tip_cents
        ref = f"ORD-{d.order_id}"
        existing = db.execute(
            select(WalletTransaction).where(
                WalletTransaction.rider_id == rider_id,
                WalletTransaction.reference_number == ref,
            )
        ).scalar_one_or_none()
        if existing:
            continue
        amount = d.earning_cents + d.tip_cents
        if amount <= 0:
            continue
        db.add(WalletTransaction(
            rider_id=rider_id,
            txn_type="order_earning",
            amount_cents=amount,
            status="completed",
            reference_number=ref,
            title=f"Order DM-{8800 + d.order_id} Payout",
            subtitle=f"Delivered • #{8800 + d.order_id}",
            order_id=d.order_id,
        ))
        wallet.total_balance_cents += amount
    wallet.locked_balance_cents = locked
    _recalculate_available(db, wallet)


def seed_wallet_demo(db: Session, rider_id: int) -> None:
    wallet = _get_or_create_wallet(db, rider_id)
    if db.execute(
        select(WalletTransaction).where(
            WalletTransaction.rider_id == rider_id,
            WalletTransaction.reference_number == "WD-89214",
        )
    ).scalar_one_or_none():
        return

    now = utcnow()
    demos = [
        ("withdrawal", -150000, "processing", "WD-89214", "Instant Withdrawal", "Today, 05:15 PM • #WD-89214", None, now - timedelta(hours=2)),
        ("order_earning", 18500, "completed", "ORD-42", "Order DM-8842 Payout", "Today, 08:42 PM • Delivered", 42, now - timedelta(hours=1)),
        ("incentive", 25000, "completed", "INC-8842", "Peak Dinner Rush Incentive", "Today, 04:30 PM • 8 Orders Milestone", None, now - timedelta(hours=5)),
        ("weekly_payout", -864000, "completed", "WD-98402", "Weekly Payout Auto-Withdrawal", "Yesterday, 11:00 AM • #WD-98402", None, now - timedelta(days=1, hours=3)),
        ("order_earning", 14200, "completed", "ORD-19", "Order DM-8819 Payout", "Yesterday, 06:15 PM • Delivered", 19, now - timedelta(days=1, hours=8)),
    ]
    for txn_type, amount, status, ref, title, subtitle, order_id, created in demos:
        db.add(WalletTransaction(
            rider_id=rider_id,
            txn_type=txn_type,
            amount_cents=amount,
            status=status,
            reference_number=ref,
            title=title,
            subtitle=subtitle,
            order_id=order_id,
            created_at=created,
            updated_at=created,
        ))
    wallet.locked_balance_cents = 42000
    wallet.total_balance_cents = 345000
    wallet.available_balance_cents = 303000
