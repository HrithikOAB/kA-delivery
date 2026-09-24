"""Admin dashboard API: verification, partners, operations, orders, and the
admin-only test-order tool. All endpoints require an authenticated admin and are
further gated by admin permission tier (see ``api/deps``).
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_admin_permission
from app.database import get_db
from app.models.enums import AdminRole, ApprovalStatus
from app.models.rider_document import RiderDocument
from app.models.user import RiderProfile, User
from app.models.delivery import Delivery, DeliveryBatch
from app.models.delivery_issue import DeliveryIssue
from datetime import datetime, timedelta, timezone

from app.models.enums import (
    ACTIVE_ORDER_STATUSES,
    BatchStatus,
    DeliveryIssueStatus,
    DeliveryStatus,
    OrderStatus,
    PayoutStatus,
)
from app.models.mess import Mess
from app.models.order import Order
from app.schemas.maps import PlaceAutocompleteIn, PlaceDetailsOut, PlaceSuggestionOut
from app.schemas.admin import (
    FleetLeaderOut,
    ActiveDeliveryOut,
    AdminDeliveryRow,
    AssignRequest,
    AuditEventOut,
    NoteRequest,
    OrderDetailOut,
    OrderSummaryOut,
    OverviewMetrics,
    OverviewOut,
    Page,
    PartnerApplicationDetail,
    PartnerApplicationOut,
    PartnerDetail,
    PartnerUpdateRequest,
    PartnerListItem,
    ReasonRequest,
    RiderMarkerOut,
    TestDeliveryCreate,
    TestDeliveryOut,
    WithdrawalRequestOut,
    WithdrawalSummaryOut,
    WithdrawalDetailOut,
    BulkWithdrawalApproveRequest,
)
from app.schemas.partner import DeliveryIssueOut, RiderDocumentOut
from app.services import (
    audit_service,
    location_service,
    maps_service,
    wallet_service,
    document_service,
    test_order_service,
    tracking_service,
    verification_service,
    withdrawal_admin_service,
    partner_admin_service,
)

router = APIRouter(prefix="/admin", tags=["admin"])

# Permission tiers used across this module.
_verify = require_admin_permission(AdminRole.partner_verification)
_ops = require_admin_permission(AdminRole.operations)
# Reading dashboards is available to any admin tier.
_any_admin = require_admin_permission(
    AdminRole.partner_verification, AdminRole.operations, AdminRole.support
)


# --- Partner verification -------------------------------------------------

def _application_out(db: Session, profile: RiderProfile) -> PartnerApplicationOut:
    user = db.get(User, profile.user_id)
    doc_count = db.execute(
        select(func.count(RiderDocument.id)).where(
            RiderDocument.rider_id == profile.user_id
        )
    ).scalar_one()
    return PartnerApplicationOut(
        rider_id=profile.user_id,
        full_name=user.full_name if user else "",
        email=user.email if user else None,
        phone=user.phone if user else None,
        vehicle_type=profile.vehicle_type,
        vehicle_number=profile.vehicle_number,
        license_number=profile.license_number,
        approval_status=profile.approval_status,
        correction_reason=profile.correction_reason,
        document_count=doc_count,
        is_online=profile.is_online,
        created_at=profile.created_at,
    )


@router.get("/applications", response_model=Page[PartnerApplicationOut])
def list_applications(
    status: ApprovalStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(_verify),
    db: Session = Depends(get_db),
) -> Page[PartnerApplicationOut]:
    base = select(RiderProfile)
    count_q = select(func.count(RiderProfile.id))
    if status is not None:
        if status == ApprovalStatus.submitted:
            statuses = [ApprovalStatus.submitted, ApprovalStatus.pending]
            base = base.where(RiderProfile.approval_status.in_(statuses))
            count_q = count_q.where(RiderProfile.approval_status.in_(statuses))
        else:
            base = base.where(RiderProfile.approval_status == status)
            count_q = count_q.where(RiderProfile.approval_status == status)
    total = db.execute(count_q).scalar_one()
    profiles = db.execute(
        base.order_by(RiderProfile.updated_at.desc()).limit(limit).offset(offset)
    ).scalars().all()
    return Page(
        items=[_application_out(db, p) for p in profiles],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/applications/{rider_id}", response_model=PartnerApplicationDetail)
def application_detail(
    rider_id: int,
    _: User = Depends(_verify),
    db: Session = Depends(get_db),
) -> PartnerApplicationDetail:
    user = db.get(User, rider_id)
    if user is None or user.rider_profile is None:
        raise HTTPException(status_code=404, detail="Partner application not found")
    base = _application_out(db, user.rider_profile)
    docs = document_service.list_for_rider(db, rider_id)
    history = audit_service.for_target(db, "partner", rider_id)
    return PartnerApplicationDetail(
        **base.model_dump(),
        documents=[RiderDocumentOut.model_validate(d) for d in docs],
        history=[AuditEventOut.model_validate(e) for e in history],
    )


@router.get("/documents/{doc_id}")
def get_document(
    doc_id: int,
    _: User = Depends(_verify),
    db: Session = Depends(get_db),
) -> FileResponse:
    doc = document_service.get(db, doc_id)
    if doc is None or not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="Document not found")
    return FileResponse(
        doc.file_path, media_type=doc.content_type, filename=doc.original_name
    )


@router.post("/applications/{rider_id}/review", response_model=PartnerApplicationDetail)
def review_application(
    rider_id: int, admin: User = Depends(_verify), db: Session = Depends(get_db)
) -> PartnerApplicationDetail:
    verification_service.start_review(db, rider_id, admin.id)
    db.commit()
    return application_detail(rider_id, admin, db)


@router.post("/applications/{rider_id}/approve", response_model=PartnerApplicationDetail)
def approve_application(
    rider_id: int, admin: User = Depends(_verify), db: Session = Depends(get_db)
) -> PartnerApplicationDetail:
    verification_service.approve(db, rider_id, admin.id)
    db.commit()
    return application_detail(rider_id, admin, db)


@router.post("/applications/{rider_id}/reject", response_model=PartnerApplicationDetail)
def reject_application(
    rider_id: int,
    data: ReasonRequest,
    admin: User = Depends(_verify),
    db: Session = Depends(get_db),
) -> PartnerApplicationDetail:
    verification_service.reject(db, rider_id, admin.id, data.reason)
    db.commit()
    return application_detail(rider_id, admin, db)


@router.post(
    "/applications/{rider_id}/request-correction",
    response_model=PartnerApplicationDetail,
)
def request_correction(
    rider_id: int,
    data: ReasonRequest,
    admin: User = Depends(_verify),
    db: Session = Depends(get_db),
) -> PartnerApplicationDetail:
    verification_service.request_correction(db, rider_id, admin.id, data.reason)
    db.commit()
    return application_detail(rider_id, admin, db)



@router.post("/maps/places/autocomplete", response_model=list[PlaceSuggestionOut])
async def places_autocomplete(
    data: PlaceAutocompleteIn,
    _: User = Depends(_ops),
) -> list[PlaceSuggestionOut]:
    """Proxy Google Places autocomplete through the backend (avoids browser referrer restrictions)."""
    try:
        rows = await maps_service.search_places(data.input)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [PlaceSuggestionOut(place_id=r["place_id"], label=r["label"], secondary=r.get("secondary")) for r in rows]


@router.get("/maps/places/{place_id}", response_model=PlaceDetailsOut)
async def places_details(
    place_id: str,
    _: User = Depends(_ops),
) -> PlaceDetailsOut:
    details = await maps_service.get_place_details(place_id)
    if details is None:
        raise HTTPException(status_code=502, detail="Could not load place details")
    return PlaceDetailsOut(**details)


# --- Admin-only test-order tool ------------------------------------------

@router.post("/test-orders", response_model=TestDeliveryOut, status_code=201)
def create_test_order(
    data: TestDeliveryCreate,
    admin: User = Depends(_ops),
    db: Session = Depends(get_db),
) -> TestDeliveryOut:
    """Create a clearly-marked TEST delivery. Appears in the backend as a normal
    (unassigned) delivery and flows through the real dispatch/tracking pipeline.
    """
    order = test_order_service.create_test_delivery(db, admin, data)
    return test_order_service.to_out(db, order)


@router.get("/test-orders", response_model=Page[TestDeliveryOut])
def list_test_orders(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(_ops),
    db: Session = Depends(get_db),
) -> Page[TestDeliveryOut]:
    total = db.execute(
        select(func.count(Order.id)).where(Order.is_test.is_(True))
    ).scalar_one()
    orders = db.execute(
        select(Order)
        .where(Order.is_test.is_(True))
        .order_by(Order.id.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    return Page(
        items=[test_order_service.to_out(db, o) for o in orders],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/test-orders/{order_id}/advance", response_model=TestDeliveryOut)
def advance_test_order(
    order_id: int,
    to: str = Query(..., description="accept | prepare | ready"),
    admin: User = Depends(_ops),
    db: Session = Depends(get_db),
) -> TestDeliveryOut:
    order = test_order_service.advance(db, order_id, admin, to)
    return test_order_service.to_out(db, order)


@router.post("/test-orders/{order_id}/assign", response_model=TestDeliveryOut)
def assign_test_order(
    order_id: int,
    data: AssignRequest,
    admin: User = Depends(_ops),
    db: Session = Depends(get_db),
) -> TestDeliveryOut:
    order = test_order_service.assign_to_rider(db, order_id, admin, data.rider_id)
    return test_order_service.to_out(db, order)


@router.post("/test-orders/{order_id}/cancel", response_model=TestDeliveryOut)
def cancel_test_order(
    order_id: int,
    admin: User = Depends(_ops),
    db: Session = Depends(get_db),
) -> TestDeliveryOut:
    order = test_order_service.cancel(db, order_id, admin)
    return test_order_service.to_out(db, order)


# --- Overview -------------------------------------------------------------

def _issue_out(issue: DeliveryIssue) -> DeliveryIssueOut:
    return DeliveryIssueOut.model_validate(issue)


@router.get("/overview", response_model=OverviewOut)
def overview(_: User = Depends(_any_admin), db: Session = Depends(get_db)) -> OverviewOut:
    def count(stmt) -> int:
        return db.execute(stmt).scalar_one()

    pending = count(
        select(func.count(RiderProfile.id)).where(
            RiderProfile.approval_status.in_(
                [ApprovalStatus.submitted, ApprovalStatus.under_review, ApprovalStatus.pending]
            )
        )
    )
    approved = count(
        select(func.count(RiderProfile.id)).where(
            RiderProfile.approval_status == ApprovalStatus.approved
        )
    )
    online = count(
        select(func.count(RiderProfile.id)).where(RiderProfile.is_online.is_(True))
    )
    active = count(
        select(func.count(Order.id)).where(Order.status.in_(list(ACTIVE_ORDER_STATUSES)))
    )
    unassigned = count(
        select(func.count(DeliveryBatch.id)).where(
            DeliveryBatch.rider_id.is_(None),
            DeliveryBatch.status.in_([BatchStatus.open, BatchStatus.offered]),
        )
    )
    open_issues = count(
        select(func.count(DeliveryIssue.id)).where(
            DeliveryIssue.status != DeliveryIssueStatus.resolved
        )
    )
    recent_profiles = db.execute(
        select(RiderProfile)
        .where(
            RiderProfile.approval_status.in_(
                [ApprovalStatus.submitted, ApprovalStatus.under_review, ApprovalStatus.pending]
            )
        )
        .order_by(RiderProfile.updated_at.desc())
        .limit(5)
    ).scalars().all()
    recent_issues = db.execute(
        select(DeliveryIssue).order_by(DeliveryIssue.id.desc()).limit(5)
    ).scalars().all()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    orders_today = count(
        select(func.count(Order.id)).where(Order.created_at >= today_start)
    )
    gmv_today = db.execute(
        select(func.coalesce(func.sum(Order.total_cents), 0)).where(
            Order.created_at >= today_start
        )
    ).scalar_one()
    kitchen_statuses = {
        OrderStatus.placed,
        OrderStatus.accepted,
        OrderStatus.preparing,
        OrderStatus.ready,
    }
    active_orders = db.execute(
        select(Order).where(Order.status.in_(list(ACTIVE_ORDER_STATUSES)))
    ).scalars().all()
    live_kitchen = sum(1 for o in active_orders if o.status in kitchen_statuses)
    live_picked_up = sum(1 for o in active_orders if o.status == OrderStatus.picked_up)
    live_en_route = sum(
        1
        for o in active_orders
        if o.status in {OrderStatus.assigned, OrderStatus.out_for_delivery}
    )
    approved_profiles = db.execute(
        select(RiderProfile).where(RiderProfile.approval_status == ApprovalStatus.approved)
    ).scalars().all()
    leader_items = sorted(
        [_partner_list_item(db, p) for p in approved_profiles],
        key=lambda item: item.total_deliveries,
        reverse=True,
    )[:3]
    fleet_leaders = [
        FleetLeaderOut(
            rider_id=item.rider_id,
            full_name=item.full_name,
            total_deliveries=item.total_deliveries,
            is_online=item.is_online,
        )
        for item in leader_items
    ]

    return OverviewOut(
        metrics=OverviewMetrics(
            pending_applications=pending,
            approved_partners=approved,
            online_partners=online,
            active_deliveries=active,
            unassigned_orders=unassigned,
            delayed_or_issue_deliveries=open_issues,
            orders_today=orders_today,
            gmv_today_cents=int(gmv_today or 0),
            live_kitchen=live_kitchen,
            live_picked_up=live_picked_up,
            live_en_route=live_en_route,
            platform_revenue_cents=int((gmv_today or 0) * 0.12),
        ),
        recent_applications=[_application_out(db, p) for p in recent_profiles],
        recent_issues=[_issue_out(i) for i in recent_issues],
        fleet_leaders=fleet_leaders,
    )


# --- Partner management ---------------------------------------------------

def _current_batch_id(db: Session, rider_id: int) -> int | None:
    batch = db.execute(
        select(DeliveryBatch).where(
            DeliveryBatch.rider_id == rider_id,
            DeliveryBatch.status.in_([BatchStatus.assigned, BatchStatus.picked_up]),
        )
    ).scalars().first()
    return batch.id if batch else None


def _partner_list_item(db: Session, profile: RiderProfile) -> PartnerListItem:
    user = db.get(User, profile.user_id)
    total = db.execute(
        select(func.count(Delivery.id)).where(
            Delivery.rider_id == profile.user_id,
            Delivery.status == DeliveryStatus.delivered,
        )
    ).scalar_one()
    week_start = datetime.now(timezone.utc) - timedelta(days=7)
    week_earnings = db.execute(
        select(func.coalesce(func.sum(Delivery.earning_cents), 0)).where(
            Delivery.rider_id == profile.user_id,
            Delivery.status == DeliveryStatus.delivered,
            Delivery.delivered_at >= week_start,
        )
    ).scalar_one()
    payout_pending = db.execute(
        select(func.count(Delivery.id)).where(
            Delivery.rider_id == profile.user_id,
            Delivery.payout_status == PayoutStatus.pending,
        )
    ).scalar_one() > 0
    active_order = db.execute(
        select(Order.id)
        .join(Delivery, Delivery.order_id == Order.id)
        .where(
            Delivery.rider_id == profile.user_id,
            Order.status.in_(ACTIVE_ORDER_STATUSES),
        )
        .order_by(Order.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    wallet = wallet_service.build_wallet(db, profile.user_id)
    latest = location_service.latest_location(db, profile.user_id)
    return PartnerListItem(
        rider_id=profile.user_id,
        full_name=user.full_name if user else "",
        email=user.email if user else None,
        phone=user.phone if user else None,
        approval_status=profile.approval_status,
        is_online=profile.is_online,
        account_active=bool(user and user.is_active),
        suspended_reason=user.suspended_reason if user else None,
        current_batch_id=_current_batch_id(db, profile.user_id),
        total_deliveries=total,
        partner_code=profile.partner_code,
        rating=round(float(profile.rating or 5.0), 2),
        vehicle_type=profile.vehicle_type,
        vehicle_model=profile.vehicle_model or profile.vehicle_type.title(),
        vehicle_number=profile.vehicle_number,
        operating_hub=profile.operating_hub,
        wallet_balance_cents=int(wallet["available_balance_cents"]),
        week_earnings_cents=int(week_earnings or 0),
        payout_pending=bool(payout_pending),
        active_order_id=active_order,
        last_lat=profile.last_lat,
        last_lng=profile.last_lng,
        location_updated_at=latest.server_timestamp if latest else None,
        location_is_stale=location_service.is_stale(latest) if latest else True,
    )


@router.get("/partners", response_model=Page[PartnerListItem])
def list_partners(
    q: str | None = Query(default=None, description="search name/email/phone"),
    status: ApprovalStatus | None = None,
    online: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(_any_admin),
    db: Session = Depends(get_db),
) -> Page[PartnerListItem]:
    stmt = select(RiderProfile).join(User, User.id == RiderProfile.user_id)
    count_stmt = select(func.count(RiderProfile.id)).join(
        User, User.id == RiderProfile.user_id
    )
    if status is not None:
        stmt = stmt.where(RiderProfile.approval_status == status)
        count_stmt = count_stmt.where(RiderProfile.approval_status == status)
    if online is not None:
        stmt = stmt.where(RiderProfile.is_online.is_(online))
        count_stmt = count_stmt.where(RiderProfile.is_online.is_(online))
    if q:
        like = f"%{q.strip()}%"
        cond = (User.full_name.ilike(like)) | (User.email.ilike(like)) | (User.phone.ilike(like))
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    total = db.execute(count_stmt).scalar_one()
    profiles = db.execute(
        stmt.order_by(RiderProfile.updated_at.desc()).limit(limit).offset(offset)
    ).scalars().all()
    return Page(
        items=[_partner_list_item(db, p) for p in profiles],
        total=total, limit=limit, offset=offset,
    )


@router.get("/partners/{rider_id}", response_model=PartnerDetail)
def partner_detail(
    rider_id: int, _: User = Depends(_any_admin), db: Session = Depends(get_db)
) -> PartnerDetail:
    user = db.get(User, rider_id)
    if user is None or user.rider_profile is None:
        raise HTTPException(status_code=404, detail="Partner not found")
    profile = user.rider_profile
    base = _partner_list_item(db, profile).model_dump()
    base.update({
        "license_number": profile.license_number,
        "correction_reason": profile.correction_reason,
        "fleet_tier": profile.fleet_tier,
        "bank_name": profile.bank_name,
        "bank_account_masked": profile.bank_account_masked,
        "upi_linked": profile.upi_linked,
        "phone_verified": profile.phone_verified,
        "rc_status": profile.rc_status,
        "documents_valid_until": profile.documents_valid_until,
    })
    payload = partner_admin_service.get_profile(db, rider_id, base)
    from app.schemas.partner import RiderDocumentOut
    payload["documents"] = [RiderDocumentOut.model_validate(d) for d in payload.pop("documents")]
    payload["open_issues"] = [_issue_out(i) for i in payload.pop("open_issues")]
    payload["history"] = [AuditEventOut.model_validate(e) for e in payload.pop("history")]
    return PartnerDetail.model_validate(payload)


@router.patch("/partners/{rider_id}", response_model=PartnerDetail)
def update_partner_profile(
    rider_id: int, data: PartnerUpdateRequest, admin: User = Depends(_any_admin), db: Session = Depends(get_db),
) -> PartnerDetail:
    partner_admin_service.update_partner(db, rider_id, admin.id, data.model_dump(exclude_unset=True))
    return partner_detail(rider_id, admin, db)


@router.post("/partners/{rider_id}/notes", response_model=PartnerDetail)
def add_partner_note(
    rider_id: int, data: ReasonRequest, admin: User = Depends(_any_admin), db: Session = Depends(get_db),
) -> PartnerDetail:
    partner_admin_service.add_admin_note(db, rider_id, admin.id, data.reason)
    return partner_detail(rider_id, admin, db)


@router.post("/partners/{rider_id}/suspend", response_model=PartnerDetail)
def suspend_partner(
    rider_id: int, data: ReasonRequest, admin: User = Depends(_any_admin),
    db: Session = Depends(get_db),
) -> PartnerDetail:
    user = db.get(User, rider_id)
    if user is None or user.rider_profile is None:
        raise HTTPException(status_code=404, detail="Partner not found")
    user.is_active = False
    user.suspended_reason = data.reason.strip()
    if user.rider_profile:
        user.rider_profile.is_online = False
    audit_service.record(
        db, actor_user_id=admin.id, action="partner_suspended",
        target_type="partner", target_id=rider_id, reason=data.reason.strip(),
    )
    db.commit()
    return partner_detail(rider_id, admin, db)


@router.post("/partners/{rider_id}/reactivate", response_model=PartnerDetail)
def reactivate_partner(
    rider_id: int, data: ReasonRequest, admin: User = Depends(_any_admin),
    db: Session = Depends(get_db),
) -> PartnerDetail:
    user = db.get(User, rider_id)
    if user is None or user.rider_profile is None:
        raise HTTPException(status_code=404, detail="Partner not found")
    user.is_active = True
    user.suspended_reason = None
    audit_service.record(
        db, actor_user_id=admin.id, action="partner_reactivated",
        target_type="partner", target_id=rider_id, reason=data.reason.strip(),
    )
    db.commit()
    return partner_detail(rider_id, admin, db)


# --- Orders & issues ------------------------------------------------------

def _order_summary(db: Session, order: Order) -> OrderSummaryOut:
    mess = db.get(Mess, order.mess_id)
    customer = db.get(User, order.customer_id)
    delivery = db.execute(
        select(Delivery).where(Delivery.order_id == order.id)
    ).scalar_one_or_none()
    rider = db.get(User, delivery.rider_id) if delivery and delivery.rider_id else None
    return OrderSummaryOut(
        order_id=order.id, is_test=order.is_test, status=order.status.value,
        mess_name=mess.name if mess else None,
        customer_name=customer.full_name if customer else None,
        rider_name=rider.full_name if rider else None,
        delivery_status=delivery.status.value if delivery else None,
        total_cents=order.total_cents, created_at=order.created_at,
    )


@router.get("/orders", response_model=Page[OrderSummaryOut])
def list_orders(
    q: str | None = Query(default=None, description="order id or partner name"),
    status: OrderStatus | None = None,
    is_test: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(_any_admin),
    db: Session = Depends(get_db),
) -> Page[OrderSummaryOut]:
    stmt = select(Order)
    count_stmt = select(func.count(Order.id))
    if status is not None:
        stmt = stmt.where(Order.status == status)
        count_stmt = count_stmt.where(Order.status == status)
    if is_test is not None:
        stmt = stmt.where(Order.is_test.is_(is_test))
        count_stmt = count_stmt.where(Order.is_test.is_(is_test))
    if q and q.strip().isdigit():
        stmt = stmt.where(Order.id == int(q.strip()))
        count_stmt = count_stmt.where(Order.id == int(q.strip()))
    total = db.execute(count_stmt).scalar_one()
    orders = db.execute(
        stmt.order_by(Order.id.desc()).limit(limit).offset(offset)
    ).scalars().all()
    return Page(
        items=[_order_summary(db, o) for o in orders],
        total=total, limit=limit, offset=offset,
    )


@router.get("/orders/{order_id}", response_model=OrderDetailOut)
def order_detail(
    order_id: int, _: User = Depends(_any_admin), db: Session = Depends(get_db)
) -> OrderDetailOut:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    summary = _order_summary(db, order)
    timeline = audit_service.for_order(db, order_id)
    issues = db.execute(
        select(DeliveryIssue).where(DeliveryIssue.order_id == order_id)
        .order_by(DeliveryIssue.id.desc())
    ).scalars().all()
    return OrderDetailOut(
        **summary.model_dump(),
        dropoff_text=order.address_text,
        timeline=[AuditEventOut.model_validate(e) for e in timeline],
        issues=[_issue_out(i) for i in issues],
    )


@router.get("/issues", response_model=Page[DeliveryIssueOut])
def list_issues(
    status: DeliveryIssueStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(_any_admin),
    db: Session = Depends(get_db),
) -> Page[DeliveryIssueOut]:
    stmt = select(DeliveryIssue)
    count_stmt = select(func.count(DeliveryIssue.id))
    if status is not None:
        stmt = stmt.where(DeliveryIssue.status == status)
        count_stmt = count_stmt.where(DeliveryIssue.status == status)
    total = db.execute(count_stmt).scalar_one()
    issues = db.execute(
        stmt.order_by(DeliveryIssue.id.desc()).limit(limit).offset(offset)
    ).scalars().all()
    return Page(
        items=[_issue_out(i) for i in issues], total=total, limit=limit, offset=offset
    )


@router.post("/issues/{issue_id}/note", response_model=DeliveryIssueOut)
def add_issue_note(
    issue_id: int, data: NoteRequest, admin: User = Depends(_any_admin),
    db: Session = Depends(get_db),
) -> DeliveryIssueOut:
    issue = db.get(DeliveryIssue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    issue.admin_note = data.note.strip()
    if issue.status == DeliveryIssueStatus.open:
        issue.status = DeliveryIssueStatus.acknowledged
    audit_service.record(
        db, actor_user_id=admin.id, action="issue_note_added",
        target_type="issue", target_id=issue.id, detail=data.note.strip()[:200],
        order_id=issue.order_id, delivery_id=issue.delivery_id,
    )
    db.commit()
    db.refresh(issue)
    return _issue_out(issue)


@router.post("/issues/{issue_id}/resolve", response_model=DeliveryIssueOut)
def resolve_issue(
    issue_id: int, admin: User = Depends(_any_admin), db: Session = Depends(get_db)
) -> DeliveryIssueOut:
    issue = db.get(DeliveryIssue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    issue.status = DeliveryIssueStatus.resolved
    issue.resolved_by_user_id = admin.id
    audit_service.record(
        db, actor_user_id=admin.id, action="issue_resolved",
        target_type="issue", target_id=issue.id,
        order_id=issue.order_id, delivery_id=issue.delivery_id,
    )
    db.commit()
    db.refresh(issue)
    return _issue_out(issue)


# --- Live operations map --------------------------------------------------

@router.get("/deliveries/active", response_model=list[ActiveDeliveryOut])
def active_deliveries(
    is_test: bool | None = None,
    _: User = Depends(_any_admin),
    db: Session = Depends(get_db),
) -> list[ActiveDeliveryOut]:
    """Active deliveries with the latest rider marker + staleness.

    Reuses ``tracking_service.build_snapshot`` (the same data customers see);
    no second tracking system.
    """
    stmt = select(Order).where(Order.status.in_(list(ACTIVE_ORDER_STATUSES)))
    if is_test is not None:
        stmt = stmt.where(Order.is_test.is_(is_test))
    orders = db.execute(stmt.order_by(Order.id.desc())).scalars().all()
    out: list[ActiveDeliveryOut] = []
    for order in orders:
        snap = tracking_service.build_snapshot(db, order)
        delivery = db.execute(
            select(Delivery).where(Delivery.order_id == order.id)
        ).scalar_one_or_none()
        rider = db.get(User, delivery.rider_id) if delivery and delivery.rider_id else None
        marker = None
        if snap.rider_location is not None:
            m = snap.rider_location
            marker = RiderMarkerOut(
                lat=m.lat, lng=m.lng, heading=m.heading, speed=m.speed,
                server_timestamp=m.server_timestamp, is_stale=m.is_stale,
                age_seconds=m.age_seconds,
            )
        out.append(ActiveDeliveryOut(
            order_id=order.id,
            delivery_id=delivery.id if delivery else None,
            is_test=order.is_test,
            order_status=order.status.value,
            delivery_status=delivery.status.value if delivery else None,
            rider_id=rider.id if rider else None,
            rider_name=rider.full_name if rider else None,
            pickup_lat=snap.mess_lat, pickup_lng=snap.mess_lng, pickup_label=snap.mess_name,
            dropoff_lat=snap.dropoff_lat, dropoff_lng=snap.dropoff_lng,
            dropoff_text=snap.dropoff_text,
            rider_marker=marker, eta_minutes=snap.eta_minutes, distance_km=snap.distance_km,
        ))
    return out


@router.get("/orders/{order_id}/tracking")
def order_tracking(
    order_id: int, admin: User = Depends(_any_admin), db: Session = Depends(get_db)
):
    """Admin order-scoped tracking snapshot (reuses the customer snapshot)."""
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if not tracking_service.admin_can_view(order, admin):
        raise HTTPException(status_code=403, detail="Not authorized")
    return tracking_service.build_snapshot(db, order)

# --- Withdrawal requests --------------------------------------------------

@router.get("/withdrawals/summary", response_model=WithdrawalSummaryOut)
def withdrawals_summary(_: User = Depends(_any_admin), db: Session = Depends(get_db)) -> WithdrawalSummaryOut:
    return WithdrawalSummaryOut.model_validate(withdrawal_admin_service.summary(db))


@router.get("/withdrawals", response_model=Page[WithdrawalRequestOut])
def list_withdrawals(
    status: str | None = Query(default=None, description="all|pending_review|approved|rejected"),
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(_any_admin),
    db: Session = Depends(get_db),
) -> Page[WithdrawalRequestOut]:
    items, total = withdrawal_admin_service.list_requests(db, status=status, q=q, limit=limit, offset=offset)
    return Page(items=[WithdrawalRequestOut.model_validate(i) for i in items], total=total, limit=limit, offset=offset)




@router.get("/withdrawals/{txn_id}", response_model=WithdrawalDetailOut)
def withdrawal_detail(txn_id: int, _: User = Depends(_any_admin), db: Session = Depends(get_db)) -> WithdrawalDetailOut:
    return WithdrawalDetailOut.model_validate(withdrawal_admin_service.get_detail(db, txn_id))

@router.post("/withdrawals/{txn_id}/approve", response_model=WithdrawalRequestOut)
def approve_withdrawal(txn_id: int, admin: User = Depends(_any_admin), db: Session = Depends(get_db)) -> WithdrawalRequestOut:
    return WithdrawalRequestOut.model_validate(withdrawal_admin_service.approve(db, txn_id, admin.id))


@router.post("/withdrawals/{txn_id}/reject", response_model=WithdrawalRequestOut)
def reject_withdrawal(txn_id: int, data: ReasonRequest, admin: User = Depends(_any_admin), db: Session = Depends(get_db)) -> WithdrawalRequestOut:
    return WithdrawalRequestOut.model_validate(withdrawal_admin_service.reject(db, txn_id, admin.id, data.reason))


@router.post("/withdrawals/bulk-approve")
def bulk_approve_withdrawals(data: BulkWithdrawalApproveRequest, admin: User = Depends(_any_admin), db: Session = Depends(get_db)):
    return withdrawal_admin_service.bulk_approve(db, data.ids, admin.id)
