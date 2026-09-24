"""Rider availability, offers, location ingestion and earnings."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_approved_rider, require_rider
from app.database import get_db
from app.models.delivery import Delivery, DeliveryBatch, DeliveryOffer
from app.models.delivery_issue import DeliveryIssue
from app.models.support_ticket import SupportTicket
from app.models.enums import (
    ApprovalStatus,
    BatchStatus,
    DeliveryStatus,
    OfferStatus,
    OrderStatus,
)
from app.models.mess import Mess
from app.models.order import Order
from app.models.user import User
from app.schemas.delivery import (
    ActiveDeliveryMetaOut,
    BatchOut,
    DeliveryStop,
    EarningsDetailOut,
    EarningsResponse,
    CashoutResultOut,
    HotspotOut,
    IncentiveQuestOut,
    OfferDetailOut,
    OfferOut,
    RiderDashboardOut,
    DashboardQuestOut,
    LastCompletedOut,
    SurgeHotspotOut,
    RiderOrderItemOut,
)
from app.schemas.partner import (
    DeliveryHistoryOut,
    DeliveryIssueOut,
    ReportIssueRequest,
    RiderDocumentOut,
    RiderProfileDetailOut,
    RiderProfileUpdate,
    SupportHelpOut,
    SupportTicketOut,
    VerificationStatusOut,
    WalletOut,
    WalletTransactionsOut,
    WalletWithdrawOut,
    WalletWithdrawRequest,
)
from app.schemas.tracking import LocationAccepted, LocationIn
from app.services import (
    active_delivery_service,
    auth_service,
    dispatch_service,
    dashboard_service,
    document_service,
    profile_service,
    earnings_service,
    history_service,
    location_service,
    prep_service,
    offer_detail_service,
    pricing_service,
    verification_service,
    wallet_service,
    support_service,
)
from app.services.ws_manager import manager

router = APIRouter(prefix="/rider", tags=["rider"])


# --- Verification & documents (available before approval) ----------------

def _verification_out(db: Session, user: User) -> VerificationStatusOut:
    from datetime import datetime, timezone
    from app.models.enums import DocumentStatus

    profile = user.rider_profile
    docs = document_service.list_for_rider(db, user.id)
    status = profile.approval_status if profile else ApprovalStatus.draft
    expected = 4
    accepted = sum(1 for d in docs if d.status == DocumentStatus.accepted)
    verified_pct = int(round((accepted / expected) * 100)) if expected else 0
    submitted_at = min((d.uploaded_at for d in docs), default=None) if docs else None

    if status == ApprovalStatus.approved:
        steps_completed = 3
        headline = "Verification Complete"
        subtitle = "Your account is activated. Go online and start earning."
    elif status in (ApprovalStatus.submitted, ApprovalStatus.under_review, ApprovalStatus.pending):
        steps_completed = 2
        headline = "Application Under Review"
        subtitle = (
            "Your documents have been submitted and are currently being reviewed by the "
            "Khana Delivery compliance team. Typical review time is 2-4 hours."
        )
    elif docs:
        steps_completed = 1
        headline = "Documents Uploaded"
        subtitle = "Submit your application for compliance review when all documents are ready."
    else:
        steps_completed = 0
        headline = "Complete Your Verification"
        subtitle = "Upload your compliance documents to start the review process."

    submitted_label = ""
    if submitted_at is not None:
        now = datetime.now(timezone.utc)
        st = submitted_at if submitted_at.tzinfo else submitted_at.replace(tzinfo=timezone.utc)
        if st.date() == now.date():
            submitted_label = f"Today, {st.strftime('%I:%M %p').lstrip('0')}"
        else:
            submitted_label = st.strftime('%b %d, %I:%M %p').lstrip('0')

    return VerificationStatusOut(
        approval_status=status,
        correction_reason=profile.correction_reason if profile else None,
        can_go_online=bool(profile and profile.approval_status == ApprovalStatus.approved),
        documents=[RiderDocumentOut.model_validate(d) for d in docs],
        submitted_at=submitted_at,
        submitted_label=submitted_label,
        verified_pct=verified_pct,
        steps_completed=steps_completed,
        steps_total=3,
        documents_submitted=len(docs),
        documents_expected=expected,
        status_headline=headline,
        status_subtitle=subtitle,
    )


@router.get("/verification", response_model=VerificationStatusOut)
def my_verification(
    user: User = Depends(require_rider), db: Session = Depends(get_db)
) -> VerificationStatusOut:
    return _verification_out(db, user)


@router.get("/documents", response_model=list[RiderDocumentOut])
def my_documents(
    user: User = Depends(require_rider), db: Session = Depends(get_db)
) -> list[RiderDocumentOut]:
    return [RiderDocumentOut.model_validate(d) for d in document_service.list_for_rider(db, user.id)]


@router.post("/documents", response_model=RiderDocumentOut, status_code=201)
def upload_document(
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(require_rider),
    db: Session = Depends(get_db),
) -> RiderDocumentOut:
    doc = document_service.save_upload(db, user.id, doc_type, file)
    db.commit()
    db.refresh(doc)
    return RiderDocumentOut.model_validate(doc)


@router.post("/resubmit", response_model=VerificationStatusOut)
def resubmit_application(
    user: User = Depends(require_rider), db: Session = Depends(get_db)
) -> VerificationStatusOut:
    verification_service.resubmit(db, user)
    db.commit()
    return _verification_out(db, user)


def _active_batch(db: Session, rider_id: int) -> DeliveryBatch | None:
    """Return the rider's in-progress batch (stops still pending delivery)."""
    batches = db.execute(
        select(DeliveryBatch)
        .options(selectinload(DeliveryBatch.deliveries))
        .where(
            DeliveryBatch.rider_id == rider_id,
            DeliveryBatch.status.in_(
                [BatchStatus.open, BatchStatus.assigned, BatchStatus.picked_up]
            ),
        )
        .order_by(DeliveryBatch.updated_at.desc())
    ).scalars().all()
    for batch in batches:
        if not batch.deliveries:
            dispatch_service.close_empty_batch(db, batch)
            continue
        dispatch_service.finalize_batch_if_done(db, batch)
        if not dispatch_service.batch_has_pending_deliveries(batch):
            continue
        batch = dispatch_service.rebalance_rider_active_batch(db, batch)
        if batch and dispatch_service.batch_has_pending_deliveries(batch):
            return batch
    db.flush()
    return None


@router.post("/online", status_code=204)
def go_online(user: User = Depends(require_approved_rider), db: Session = Depends(get_db)):
    auth_service.set_rider_online(db, user, True)
    dispatch_service.repair_assigned_batches(db)
    dispatch_service.retry_pending_dispatches(db)
    db.commit()


@router.post("/offline", status_code=204)
def go_offline(user: User = Depends(require_rider), db: Session = Depends(get_db)):
    if _active_batch(db, user.id) is not None:
        raise HTTPException(
            status_code=409, detail="Finish your active delivery before going offline"
        )
    auth_service.set_rider_online(db, user, False)


@router.get("/offers", response_model=list[OfferOut])
def my_offers(
    user: User = Depends(require_approved_rider), db: Session = Depends(get_db)
) -> list[OfferOut]:
    offers = db.execute(
        select(DeliveryOffer).where(
            DeliveryOffer.rider_id == user.id,
            DeliveryOffer.status.in_([OfferStatus.sent, OfferStatus.expired]),
        )
    ).scalars().all()
    out: list[OfferOut] = []
    for offer in offers:
        batch = db.get(DeliveryBatch, offer.batch_id)
        if not dispatch_service.offer_is_actionable(offer, batch):
            continue
        mess = db.get(Mess, batch.mess_id)
        deliveries = batch.deliveries
        orders = [db.get(Order, d.order_id) for d in deliveries]
        orders = [o for o in orders if o is not None]
        earnings = pricing_service.offer_earnings(orders, len(deliveries))
        stops = _build_stops(db, batch)
        out.append(
            OfferOut(
                id=offer.id,
                batch_id=offer.batch_id,
                status=offer.status,
                sent_at=offer.sent_at,
                expires_at=offer.expires_at,
                mess_name=mess.name if mess else None,
                mess_lat=mess.lat if mess else None,
                mess_lng=mess.lng if mess else None,
                order_count=len(deliveries),
                base_earning_cents=earnings["base_earning_cents"],
                surge_cents=earnings["surge_cents"],
                incentive_cents=earnings["incentive_cents"],
                estimated_earning_cents=earnings["estimated_earning_cents"],
                is_high_demand=len(deliveries) >= 2 or earnings["surge_cents"] > 0,
                stops=stops,
            )
        )
    return out




@router.get("/offers/{offer_id}", response_model=OfferDetailOut)
def offer_detail(
    offer_id: int,
    user: User = Depends(require_approved_rider),
    db: Session = Depends(get_db),
) -> OfferDetailOut:
    offer = db.get(DeliveryOffer, offer_id)
    if offer is None or offer.rider_id != user.id:
        raise HTTPException(status_code=404, detail="Offer not found")
    batch = db.get(DeliveryBatch, offer.batch_id)
    if not dispatch_service.offer_is_actionable(offer, batch):
        raise HTTPException(status_code=409, detail="Offer is no longer available")
    mess = db.get(Mess, batch.mess_id)
    deliveries = batch.deliveries
    orders = [db.get(Order, d.order_id) for d in deliveries]
    orders = [o for o in orders if o is not None]
    earnings = pricing_service.offer_earnings(orders, len(deliveries))
    stops = _build_stops(db, batch)
    data = offer_detail_service.build_offer_detail(offer, batch, mess, orders, stops, earnings)
    return OfferDetailOut.model_validate(data)

@router.get("/active", response_model=BatchOut | None)
def active_batch(
    user: User = Depends(require_approved_rider), db: Session = Depends(get_db)
) -> BatchOut | None:
    batch = _active_batch(db, user.id)
    if batch is None:
        return None
    return _batch_out(db, batch)


def _build_stops(db: Session, batch: DeliveryBatch) -> list[DeliveryStop]:
    stops: list[DeliveryStop] = []
    for delivery in sorted(batch.deliveries, key=lambda d: d.sequence):
        order = db.get(Order, delivery.order_id)
        if order is None:
            continue
        customer = db.get(User, order.customer_id)
        extra = active_delivery_service.enrich_stop(order, delivery, customer)
        stops.append(
            DeliveryStop(
                delivery_id=delivery.id,
                order_id=order.id,
                status=delivery.status,
                order_status=order.status,
                sequence=delivery.sequence,
                customer_name=customer.full_name if customer else "Customer",
                address_text=order.address_text,
                address_lat=order.address_lat,
                address_lng=order.address_lng,
                total_cents=order.total_cents,
                payment_method=order.payment_method,
                items=[
                    RiderOrderItemOut(
                        name=item.name_snapshot,
                        quantity=item.quantity,
                        line_total_cents=item.line_total_cents,
                    )
                    for item in order.items
                ],
                prep_ready_in_minutes=prep_service.prep_ready_in_minutes(order),
                **extra,
            )
        )
    return stops


def _batch_out(db: Session, batch: DeliveryBatch) -> BatchOut:
    mess = db.get(Mess, batch.mess_id)
    stops = _build_stops(db, batch)
    active = None
    next_delivery = next((d for d in sorted(batch.deliveries, key=lambda d: d.sequence) if d.status != DeliveryStatus.delivered), None)
    if next_delivery is not None:
        order = db.get(Order, next_delivery.order_id)
        if order is not None:
            active = ActiveDeliveryMetaOut.model_validate(
                active_delivery_service.build_active_meta(db, batch, batch.rider_id, next_delivery, order)
            )
    return BatchOut(
        id=batch.id,
        status=batch.status,
        mess_id=mess.id,
        mess_name=mess.name,
        mess_lat=mess.lat,
        mess_lng=mess.lng,
        picked_up_at=batch.picked_up_at,
        stops=stops,
        active=active,
    )


@router.post("/location", response_model=LocationAccepted)
def post_location(
    data: LocationIn,
    user: User = Depends(require_approved_rider),
    db: Session = Depends(get_db),
) -> LocationAccepted:
    """Ingest a rider location while online (idle or on an active delivery).

    Positions are validated before storage. Customer WebSocket updates are sent
    only when the rider has an active batch with undelivered stops.
    """
    if user.rider_profile is None or not user.rider_profile.is_online:
        raise HTTPException(status_code=409, detail="Rider is not online")
    batch = _active_batch(db, user.id)

    active_order_id = None
    if batch is not None:
        active_order_id = next(
            (
                d.order_id
                for d in sorted(batch.deliveries, key=lambda d: d.sequence)
                if d.status != DeliveryStatus.delivered
            ),
            None,
        )

    result = location_service.validate_and_store(
        db,
        user.id,
        active_order_id,
        lat=data.lat,
        lng=data.lng,
        client_timestamp=data.client_timestamp,
        accuracy=data.accuracy,
        heading=data.heading,
        speed=data.speed,
    )
    if not result.accepted:
        # Reject implausible data with 422 so the client can decide to resend.
        raise HTTPException(status_code=422, detail=result.reason)

    db.commit()
    if batch is not None:
        for delivery in batch.deliveries:
            if delivery.status != DeliveryStatus.delivered:
                manager.publish(delivery.order_id)

    return LocationAccepted(accepted=True, server_timestamp=result.server_timestamp)


@router.get("/earnings", response_model=EarningsResponse)
def earnings(
    user: User = Depends(require_approved_rider), db: Session = Depends(get_db)
) -> EarningsResponse:
    return earnings_service.summary_for_rider(db, user.id)


@router.get("/earnings/detail", response_model=EarningsDetailOut)
def earnings_detail(
    view: str = "weekly",
    user: User = Depends(require_approved_rider),
    db: Session = Depends(get_db),
) -> EarningsDetailOut:
    if view not in ("weekly", "daily"):
        raise HTTPException(status_code=400, detail="view must be weekly or daily")
    return EarningsDetailOut.model_validate(
        earnings_service.detail_for_rider(db, user.id, view=view)
    )


@router.post("/earnings/cashout", response_model=CashoutResultOut)
def earnings_cashout(
    user: User = Depends(require_approved_rider),
    db: Session = Depends(get_db),
) -> CashoutResultOut:
    result = earnings_service.instant_cashout(db, user.id)
    return CashoutResultOut(**result)




@router.get("/wallet", response_model=WalletOut)
def wallet_details(
    user: User = Depends(require_approved_rider),
    db: Session = Depends(get_db),
) -> WalletOut:
    wallet_service.sync_from_deliveries(db, user.id)
    db.commit()
    return WalletOut.model_validate(wallet_service.build_wallet(db, user.id))


@router.get("/wallet/transactions", response_model=WalletTransactionsOut)
def wallet_transactions(
    filter: str = "all",
    user: User = Depends(require_approved_rider),
    db: Session = Depends(get_db),
) -> WalletTransactionsOut:
    if filter not in ("all", "withdrawals", "earnings", "incentives"):
        raise HTTPException(status_code=400, detail="Invalid filter")
    return WalletTransactionsOut.model_validate(
        wallet_service.list_transactions(db, user.id, filter=filter)
    )


@router.post("/wallet/withdraw", response_model=WalletWithdrawOut)
def wallet_withdraw(
    data: WalletWithdrawRequest,
    user: User = Depends(require_approved_rider),
    db: Session = Depends(get_db),
) -> WalletWithdrawOut:
    result = wallet_service.withdraw(db, user.id, data.amount_cents, data.account_id)
    db.commit()
    return WalletWithdrawOut(**result)

@router.get("/history", response_model=DeliveryHistoryOut)
def delivery_history(
    status: str = "completed",
    period: str = "this_week",
    user: User = Depends(require_approved_rider),
    db: Session = Depends(get_db),
) -> DeliveryHistoryOut:
    if status not in ("completed", "cancelled"):
        raise HTTPException(status_code=400, detail="status must be completed or cancelled")
    if period not in ("today", "yesterday", "this_week", "this_month", "all"):
        raise HTTPException(status_code=400, detail="Invalid period")
    return DeliveryHistoryOut.model_validate(
        history_service.build_history(db, user.id, status=status, period=period)
    )


@router.post("/deliveries/{delivery_id}/issues", response_model=DeliveryIssueOut, status_code=201)
def report_issue(
    delivery_id: int,
    data: ReportIssueRequest,
    user: User = Depends(require_approved_rider),
    db: Session = Depends(get_db),
) -> DeliveryIssueOut:
    """Report a problem on the rider's own active delivery (e.g. pickup delay,
    customer unavailable). Surfaces to admins in the operations dashboard.
    """
    delivery = db.get(Delivery, delivery_id)
    if delivery is None:
        raise HTTPException(status_code=404, detail="Delivery not found")
    if delivery.rider_id != user.id:
        raise HTTPException(status_code=403, detail="Not your delivery")
    issue = DeliveryIssue(
        delivery_id=delivery.id,
        order_id=delivery.order_id,
        rider_id=user.id,
        issue_type=data.issue_type.strip().lower(),
        note=data.note.strip(),
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return DeliveryIssueOut.model_validate(issue)



@router.get("/profile", response_model=RiderProfileDetailOut)
def rider_profile(
    user: User = Depends(require_rider), db: Session = Depends(get_db)
) -> RiderProfileDetailOut:
    db.flush()
    return RiderProfileDetailOut(**profile_service.build_profile(db, user))


@router.patch("/profile", response_model=RiderProfileDetailOut)
def update_rider_profile(
    data: RiderProfileUpdate,
    user: User = Depends(require_rider),
    db: Session = Depends(get_db),
) -> RiderProfileDetailOut:
    profile = user.rider_profile
    if profile is None:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    if data.app_language is not None:
        profile.app_language = data.app_language.strip()
    db.commit()
    db.refresh(user)
    return RiderProfileDetailOut(**profile_service.build_profile(db, user))

@router.get("/dashboard", response_model=RiderDashboardOut)
def rider_dashboard(
    user: User = Depends(require_approved_rider), db: Session = Depends(get_db)
) -> RiderDashboardOut:
    data = dashboard_service.build_dashboard(db, user.id)
    return RiderDashboardOut(
        hotspots=[HotspotOut(**h) for h in data["hotspots"]],
        incentive_quest=IncentiveQuestOut(**data["incentive_quest"]),
        today_deliveries=data["today_deliveries"],
        today_earnings_cents=data["today_earnings_cents"],
    )


@router.get("/support", response_model=SupportHelpOut)
def support_help(
    user: User = Depends(require_rider), db: Session = Depends(get_db)
) -> SupportHelpOut:
    support_service.seed_faqs(db)
    db.commit()
    return SupportHelpOut(**support_service.build_help_page(db, user))


@router.get("/support/tickets", response_model=list[SupportTicketOut])
def list_support_tickets(
    user: User = Depends(require_rider), db: Session = Depends(get_db)
) -> list[SupportTicketOut]:
    tickets = db.execute(
        select(SupportTicket)
        .where(SupportTicket.rider_id == user.id)
        .order_by(SupportTicket.id.desc())
        .limit(50)
    ).scalars().all()
    return [SupportTicketOut(**support_service._ticket_dict(t)) for t in tickets]


@router.post("/support/tickets", response_model=SupportTicketOut, status_code=201)
def create_support_ticket(
    category: str = Form(...),
    topic: str = Form(...),
    message: str = Form(...),
    order_id: int | None = Form(None),
    file: UploadFile | None = File(None),
    user: User = Depends(require_rider),
    db: Session = Depends(get_db),
) -> SupportTicketOut:
    ticket = support_service.create_ticket(
        db, user, category, topic, message, order_id=order_id, upload=file
    )
    db.commit()
    db.refresh(ticket)
    return SupportTicketOut(**support_service._ticket_dict(ticket))

