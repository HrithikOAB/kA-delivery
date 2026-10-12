"""Admin withdrawal request queue and approvals."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.delivery_issue import DeliveryIssue
from app.models.enums import DeliveryIssueStatus
from app.models.rider_wallet import RiderWallet
from app.models.user import RiderProfile, User
from app.models.wallet_transaction import WalletTransaction
from app.services import audit_service, wallet_service

WITHDRAWAL_TYPES = ("withdrawal", "weekly_payout")
AUTO_DISBURSE_LIMIT_CENTS = 500_000

REJECT_REASONS = [
    "Account number mismatch with KYC records",
    "Suspicious velocity / multiple requests",
    "Incomplete document verification",
    "Manual compliance hold",
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _risk_for_rider(
    db: Session, profile: RiderProfile | None, user: User | None, amount_cents: int
) -> tuple[int, str]:
    score = 98
    if not profile or not profile.phone_verified:
        score -= 12
    if user and not user.is_active:
        score -= 40
    if profile:
        open_issues = db.execute(
            select(func.count(DeliveryIssue.id)).where(
                DeliveryIssue.rider_id == profile.user_id,
                DeliveryIssue.status != DeliveryIssueStatus.resolved,
            )
        ).scalar_one()
        score -= 8 * min(open_issues, 3)
    if abs(amount_cents) > AUTO_DISBURSE_LIMIT_CENTS:
        score -= 5
    score = max(40, min(100, score))
    label = (
        "Low Risk"
        if score >= 95
        else "Moderate-Low"
        if score >= 85
        else "Moderate"
        if score >= 70
        else "Elevated"
    )
    return score, label


def _ui_status(status: str) -> str:
    if status == "processing":
        return "pending_review"
    if status in ("rejected", "flagged"):
        return "rejected"
    return "approved"


def _risk_note(score: int, profile: RiderProfile | None, user: User | None) -> str:
    if user and not user.is_active:
        return "Account suspended — manual review required"
    if score >= 95:
        return "Verified bank, stable delivery history"
    if score >= 85:
        return "Minor variance in payout pattern"
    return "Additional verification recommended"


def _enrich_txn(db: Session, txn: WalletTransaction) -> dict:
    user = db.get(User, txn.rider_id)
    profile = db.execute(
        select(RiderProfile).where(RiderProfile.user_id == txn.rider_id)
    ).scalar_one_or_none()
    wallet = wallet_service.build_wallet(db, txn.rider_id)
    amount = abs(txn.amount_cents)
    bank_name = (profile.bank_name if profile and profile.bank_name else "") or "—"
    bank_masked = (profile.bank_account_masked if profile else "") or "—"
    ifsc = (profile.ifsc_code if profile and profile.ifsc_code else "") or "—"
    risk_score, risk_label = txn.risk_score or 95, txn.risk_label or "Low Risk"
    if txn.status == "processing":
        risk_score, risk_label = _risk_for_rider(db, profile, user, txn.amount_cents)
    partner_code = profile.partner_code if profile else None
    return {
        "id": txn.id,
        "reference_number": txn.reference_number,
        "payout_cycle": txn.payout_cycle or "",
        "created_at": txn.created_at,
        "rider_id": txn.rider_id,
        "rider_name": user.full_name if user else "Partner",
        "partner_code": partner_code,
        "fleet_tier": profile.fleet_tier if profile else "",
        "rating": round(float(profile.rating), 2) if profile and profile.rating is not None else None,
        "amount_cents": amount,
        "fee_cents": txn.fee_cents,
        "net_amount_cents": max(0, amount - txn.fee_cents),
        "wallet_balance_cents": wallet["total_balance_cents"],
        "post_cashout_balance_cents": wallet["available_balance_cents"],
        "bank_name": bank_name,
        "bank_account_masked": bank_masked,
        "ifsc_code": ifsc,
        "account_holder": user.full_name if user else "Partner",
        "bank_verified": bool(profile and profile.upi_linked),
        "risk_score": risk_score,
        "risk_label": risk_label,
        "risk_note": _risk_note(risk_score, profile, user),
        "status": _ui_status(txn.status),
        "admin_note": txn.admin_note,
        "requires_dual_signoff": amount > AUTO_DISBURSE_LIMIT_CENTS,
        "auto_disburse_eligible": amount <= AUTO_DISBURSE_LIMIT_CENTS,
        "reviewed_at": txn.reviewed_at,
    }


def summary(db: Session) -> dict:
    today_start = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    base = select(WalletTransaction).where(WalletTransaction.txn_type.in_(WITHDRAWAL_TYPES))
    pending = db.execute(base.where(WalletTransaction.status == "processing")).scalars().all()
    approved_today = db.execute(
        base.where(
            WalletTransaction.status == "completed",
            WalletTransaction.reviewed_at >= today_start,
        )
    ).scalars().all()
    rejected = db.execute(
        base.where(WalletTransaction.status.in_(("rejected", "flagged")))
    ).scalars().all()
    escrow = db.execute(select(func.coalesce(func.sum(RiderWallet.total_balance_cents), 0))).scalar_one()
    pending_amount = sum(abs(t.amount_cents) for t in pending)
    return {
        "pending_count": len(pending),
        "pending_amount_cents": pending_amount,
        "approved_today_count": len(approved_today),
        "approved_today_amount_cents": sum(abs(t.amount_cents) for t in approved_today),
        "rejected_count": len(rejected),
        "rejected_amount_cents": sum(abs(t.amount_cents) for t in rejected),
        "escrow_reserve_cents": int(escrow or 0),
        "liquidity_ratio": round((escrow or 0) / max(pending_amount, 1), 1),
        "total_count": db.execute(
            select(func.count(WalletTransaction.id)).where(
                WalletTransaction.txn_type.in_(WITHDRAWAL_TYPES)
            )
        ).scalar_one(),
    }


def _db_status(status: str):
    if status == "pending_review":
        return "processing"
    if status == "approved":
        return "completed"
    if status == "rejected":
        return ["rejected", "flagged"]
    return status


def list_requests(
    db: Session,
    status: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    stmt = select(WalletTransaction).where(WalletTransaction.txn_type.in_(WITHDRAWAL_TYPES))
    count_stmt = select(func.count(WalletTransaction.id)).where(
        WalletTransaction.txn_type.in_(WITHDRAWAL_TYPES)
    )
    if status and status != "all":
        db_status = _db_status(status)
        if isinstance(db_status, list):
            stmt = stmt.where(WalletTransaction.status.in_(db_status))
            count_stmt = count_stmt.where(WalletTransaction.status.in_(db_status))
        else:
            stmt = stmt.where(WalletTransaction.status == db_status)
            count_stmt = count_stmt.where(WalletTransaction.status == db_status)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.join(User, User.id == WalletTransaction.rider_id).where(
            or_(
                User.full_name.ilike(like),
                User.phone.ilike(like),
                WalletTransaction.reference_number.ilike(like),
            )
        )
        count_stmt = count_stmt.join(User, User.id == WalletTransaction.rider_id).where(
            or_(
                User.full_name.ilike(like),
                User.phone.ilike(like),
                WalletTransaction.reference_number.ilike(like),
            )
        )
    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(
        stmt.order_by(WalletTransaction.created_at.desc()).limit(limit).offset(offset)
    ).scalars().all()
    return [_enrich_txn(db, t) for t in rows], total


def get_detail(db: Session, txn_id: int) -> dict:
    txn = db.get(WalletTransaction, txn_id)
    if txn is None or txn.txn_type not in WITHDRAWAL_TYPES:
        raise HTTPException(status_code=404, detail="Withdrawal request not found")
    base = _enrich_txn(db, txn)
    user = db.get(User, txn.rider_id)
    profile = db.execute(
        select(RiderProfile).where(RiderProfile.user_id == txn.rider_id)
    ).scalar_one_or_none()
    wallet_row = db.execute(
        select(RiderWallet).where(RiderWallet.rider_id == txn.rider_id)
    ).scalar_one_or_none()
    from app.models.rider_document import RiderDocument
    from app.models.delivery import Delivery
    from app.models.enums import DeliveryStatus

    docs = db.execute(
        select(RiderDocument).where(RiderDocument.rider_id == txn.rider_id)
    ).scalars().all()
    total_deliveries = db.execute(
        select(func.count(Delivery.id)).where(
            Delivery.rider_id == txn.rider_id,
            Delivery.status == DeliveryStatus.delivered,
        )
    ).scalar_one()
    open_disputes = db.execute(
        select(func.count(DeliveryIssue.id)).where(
            DeliveryIssue.rider_id == txn.rider_id,
            DeliveryIssue.status != DeliveryIssueStatus.resolved,
        )
    ).scalar_one()

    today_start = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    daily_limit_cents = 5_000_000
    rider_today = db.execute(
        select(WalletTransaction).where(
            WalletTransaction.rider_id == txn.rider_id,
            WalletTransaction.txn_type.in_(WITHDRAWAL_TYPES),
            WalletTransaction.created_at >= today_start,
        )
    ).scalars().all()
    daily_used = sum(abs(t.amount_cents) for t in rider_today)
    daily_remaining = max(0, daily_limit_cents - daily_used)

    gross = wallet_row.total_balance_cents if wallet_row else base["wallet_balance_cents"]
    locked = wallet_row.locked_balance_cents if wallet_row else 0
    available = wallet_row.available_balance_cents if wallet_row else base["post_cashout_balance_cents"]

    earning_rows = db.execute(
        select(WalletTransaction)
        .where(
            WalletTransaction.rider_id == txn.rider_id,
            WalletTransaction.txn_type.in_(("order_earning", "incentive")),
            WalletTransaction.amount_cents > 0,
        )
        .order_by(WalletTransaction.created_at.desc())
        .limit(12)
    ).scalars().all()
    earning_components = []
    for e in earning_rows:
        cat = "Trip Fare" if e.txn_type == "order_earning" else "Incentive"
        earning_components.append(
            {
                "reference": e.reference_number or f"#{e.id}",
                "title": e.title,
                "category": cat,
                "timestamp": e.created_at,
                "status": "Delivered" if e.txn_type == "order_earning" else "Awarded",
                "amount_cents": e.amount_cents,
            }
        )

    prev_payouts = db.execute(
        select(WalletTransaction)
        .where(
            WalletTransaction.rider_id == txn.rider_id,
            WalletTransaction.txn_type.in_(WITHDRAWAL_TYPES),
            WalletTransaction.status == "completed",
            WalletTransaction.id != txn.id,
        )
        .order_by(WalletTransaction.created_at.desc())
        .limit(8)
    ).scalars().all()
    payout_history = [
        {
            "reference_number": p.reference_number,
            "created_at": p.created_at,
            "amount_cents": abs(p.amount_cents),
            "mode": "Weekly payout" if p.txn_type == "weekly_payout" else "Bank transfer",
            "utr": "",
            "status": "Completed",
        }
        for p in prev_payouts
    ]

    doc_map = {d.doc_type: d for d in docs}
    kyc_items = [
        {
            "label": "ID proof",
            "value": "On file" if doc_map.get("id_proof") else "Missing",
            "ok": bool(doc_map.get("id_proof")),
        },
        {
            "label": "Driving license",
            "value": profile.license_number if profile and profile.license_number else "—",
            "ok": bool(profile and profile.license_number),
        },
        {
            "label": "Bank details",
            "value": profile.bank_name if profile and profile.bank_name else "—",
            "ok": bool(profile and profile.bank_account_masked),
        },
        {
            "label": "Vehicle RC",
            "value": profile.rc_status if profile and profile.rc_status else "—",
            "ok": profile.rc_status == "active" if profile else False,
        },
    ]
    kyc_pct = int(100 * sum(1 for k in kyc_items if k["ok"]) / max(len(kyc_items), 1))

    risk_score = base["risk_score"]
    trust_checks = [
        {"label": "No open disputes" if open_disputes == 0 else f"{open_disputes} open disputes", "ok": open_disputes == 0},
        {"label": "Phone verified", "ok": bool(profile and profile.phone_verified)},
        {"label": "Within daily request limit", "ok": len(rider_today) <= 3},
    ]

    return {
        **base,
        "priority_queue": base["amount_cents"] <= AUTO_DISBURSE_LIMIT_CENTS,
        "partner": {
            "rider_id": txn.rider_id,
            "full_name": user.full_name if user else "Partner",
            "partner_code": base["partner_code"],
            "operating_hub": profile.operating_hub if profile else "",
            "rating": base["rating"],
            "total_deliveries": total_deliveries,
            "active_since": user.created_at if user else None,
            "fleet_tier": profile.fleet_tier if profile else "",
            "phone": user.phone if user else None,
            "kyc_compliance_pct": kyc_pct,
            "kyc_items": kyc_items,
            "documents": [
                {"doc_type": d.doc_type, "status": d.status.value, "original_name": d.original_name}
                for d in docs
            ],
        },
        "wallet": {
            "gross_total_cents": gross,
            "escrow_locked_cents": locked,
            "available_cashout_cents": available,
            "post_withdrawal_cents": max(0, available - base["net_amount_cents"])
            if txn.status == "processing"
            else available,
            "daily_limit_cents": daily_limit_cents,
            "daily_limit_remaining_cents": daily_remaining,
            "daily_utilization_pct": round(100 * daily_used / daily_limit_cents, 1),
        },
        "bank": {
            "bank_name": base["bank_name"],
            "branch": "",
            "account_masked": base["bank_account_masked"],
            "ifsc_code": base["ifsc_code"],
            "account_holder": base["account_holder"],
            "penny_drop_verified": base["bank_verified"],
            "name_match_pct": 100 if base["bank_verified"] else None,
        },
        "earning_components": earning_components,
        "payout_history": payout_history,
        "risk": {
            "score": risk_score,
            "label": base["risk_label"],
            "checks": trust_checks,
        },
        "reject_reasons": REJECT_REASONS,
    }


def approve(db: Session, txn_id: int, admin_id: int) -> dict:
    txn = db.get(WalletTransaction, txn_id)
    if txn is None or txn.txn_type not in WITHDRAWAL_TYPES:
        raise HTTPException(status_code=404, detail="Withdrawal request not found")
    if txn.status != "processing":
        raise HTTPException(status_code=400, detail="Request is not pending review")
    txn.status = "completed"
    txn.reviewed_by_user_id = admin_id
    txn.reviewed_at = _utcnow()
    audit_service.record(
        db,
        actor_user_id=admin_id,
        action="withdrawal_approved",
        target_type="withdrawal",
        target_id=txn.id,
        reason=txn.reference_number,
    )
    db.commit()
    db.refresh(txn)
    return _enrich_txn(db, txn)


def reject(db: Session, txn_id: int, admin_id: int, reason: str) -> dict:
    txn = db.get(WalletTransaction, txn_id)
    if txn is None or txn.txn_type not in WITHDRAWAL_TYPES:
        raise HTTPException(status_code=404, detail="Withdrawal request not found")
    if txn.status != "processing":
        raise HTTPException(status_code=400, detail="Request is not pending review")
    amount = abs(txn.amount_cents)
    wallet = db.execute(
        select(RiderWallet).where(RiderWallet.rider_id == txn.rider_id)
    ).scalar_one_or_none()
    if wallet:
        wallet.total_balance_cents += amount
        wallet.available_balance_cents = max(
            0, wallet.total_balance_cents - wallet.locked_balance_cents
        )
    txn.status = "rejected"
    txn.admin_note = reason.strip()
    txn.reviewed_by_user_id = admin_id
    txn.reviewed_at = _utcnow()
    audit_service.record(
        db,
        actor_user_id=admin_id,
        action="withdrawal_rejected",
        target_type="withdrawal",
        target_id=txn.id,
        reason=reason.strip(),
    )
    db.commit()
    db.refresh(txn)
    return _enrich_txn(db, txn)


def bulk_approve(db: Session, txn_ids: list[int], admin_id: int) -> dict:
    approved, errors = [], []
    for txn_id in txn_ids:
        try:
            approved.append(approve(db, txn_id, admin_id))
        except HTTPException as exc:
            errors.append({"id": txn_id, "detail": exc.detail})
    return {"approved": approved, "errors": errors, "count": len(approved)}
