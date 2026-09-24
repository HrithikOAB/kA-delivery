"""Seed the database with demo accounts and a mess menu.

Run with:  python -m app.seed
Idempotent: it will not duplicate rows if run twice.

Demo credentials (password for all: ``password123``):
  * admin@digimess.app        — super admin (admin dashboard)
  * verifier@digimess.app     — partner-verification admin
  * ops@digimess.app          — operations admin
  * customer@digimess.app     — customer
  * rider@digimess.app        — approved rider; login/delivery OTP is always 1212
  * Pickup order is pre-seeded (new assignment at Khana Delivery Kitchen)
  * applicant@digimess.app    — rider whose application is under review (demo)
  * mess@digimess.app         — mess/kitchen owner of "Khana Delivery Kitchen"
  * combo@digimess.app        — customer + rider (to demo role switching)
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.core.security import hash_password
from app.config import settings
from app.database import SessionLocal
from app.models.enums import AdminRole, ApprovalStatus, UserRole
from app.models.mess import Mess, MenuItem
from app.models.user import Address, RiderProfile, User
from app.models.rider_document import RiderDocument
from app.models.enums import DocumentStatus
from app.models.base import utcnow

PASSWORD = "password123"

# Central demo location (Pune, IN) with nearby points.
MESS_LAT, MESS_LNG = 18.5204, 73.8567
CUST_LAT, CUST_LNG = 18.5310, 73.8446
RIDER_LAT, RIDER_LNG = 18.5250, 73.8500


def _get_or_create_user(db, email: str, **kwargs) -> tuple[User, bool]:
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user:
        return user, False
    user = User(email=email, hashed_password=hash_password(PASSWORD), **kwargs)
    db.add(user)
    db.flush()
    return user, True


def seed() -> None:
    # Assumes the schema exists (run `alembic upgrade head` first).
    with SessionLocal() as db:
        # --- Admins (no public signup; created here only) ---
        super_admin, _ = _get_or_create_user(
            db, "admin@digimess.app",
            full_name="Aditi Admin", phone="+919000000010",
            roles=UserRole.admin.value,
        )
        super_admin.admin_role = AdminRole.super_admin

        verifier, _ = _get_or_create_user(
            db, "verifier@digimess.app",
            full_name="Vikram Verifier", phone="+919000000011",
            roles=UserRole.admin.value,
        )
        verifier.admin_role = AdminRole.partner_verification

        ops, _ = _get_or_create_user(
            db, "ops@digimess.app",
            full_name="Omar Ops", phone="+919000000012",
            roles=UserRole.admin.value,
        )
        ops.admin_role = AdminRole.operations

        customer, _ = _get_or_create_user(
            db, "customer@digimess.app",
            full_name="Priya Sundaram", phone="+919000000001",
            roles=UserRole.customer.value,
        )

        rider, created_rider = _get_or_create_user(
            db, "rider@digimess.app",
            full_name="Rahul Sharma", phone="+91 98765 43210",
            roles=UserRole.rider.value,
        )
        if created_rider or rider.rider_profile is None:
            rider.rider_profile = RiderProfile(
                vehicle_type="scooter",
                vehicle_number="KA-01-EQ-9421",
                license_number="DL-0420110149646",
                approval_status=ApprovalStatus.approved,
                last_lat=RIDER_LAT,
                last_lng=RIDER_LNG,
                is_online=True,
                partner_code="DM-PARTNER-7721",
                rating=4.92,
                vehicle_model="Honda Activa 6G",
                vehicle_fuel_type="Petrol",
                vehicle_cargo_type="Standard Cargo Box",
                rc_status="active",
                phone_verified=True,
                operating_hub="Bengaluru South (Koramangala / HSR Sector 2)",
                fleet_tier="Tier 1 Gold Fleet",
                surge_priority_pct=10,
                bank_name="HDFC Bank",
                ifsc_code="HDFC0000128",
                upi_id="rahul.sharma@okhdfc",
                bank_account_masked="8839",
                upi_linked=True,
                app_language="English / ಕನ್ನಡ",
                documents_valid_until="2026",
                contact_email="rahul.delivery@digimess.in",
            )
        elif rider.rider_profile is not None:
            rp = rider.rider_profile
            rp.is_online = True
            rp.partner_code = rp.partner_code or "DM-PARTNER-7721"
            rp.rating = 4.92
            rp.vehicle_type = "scooter"
            rp.vehicle_number = "KA-01-EQ-9421"
            rp.vehicle_model = "Honda Activa 6G"
            rp.vehicle_fuel_type = "Petrol"
            rp.vehicle_cargo_type = "Standard Cargo Box"
            rp.rc_status = "active"
            rp.phone_verified = True
            rp.operating_hub = "Bengaluru South (Koramangala / HSR Sector 2)"
            rp.fleet_tier = "Tier 1 Gold Fleet"
            rp.surge_priority_pct = 10
            rp.bank_name = "HDFC Bank"
            rp.ifsc_code = "HDFC0000128"
            rp.upi_id = "rahul.sharma@okhdfc"
            rp.bank_account_masked = "8839"
            rp.upi_linked = True
            rp.app_language = "English / ಕನ್ನಡ"
            rp.documents_valid_until = "2026"
            rp.contact_email = "rahul.delivery@digimess.in"

        mess_owner, _ = _get_or_create_user(
            db, "mess@digimess.app",
            full_name="Meera Mess", phone="+919000000003",
            roles=UserRole.mess.value,
        )

        combo, created_combo = _get_or_create_user(
            db, "combo@digimess.app",
            full_name="Sam Switcher", phone="+919000000004",
            roles=f"{UserRole.customer.value},{UserRole.rider.value}",
        )
        if created_combo or combo.rider_profile is None:
            combo.rider_profile = RiderProfile(
                vehicle_type="scooter",
                vehicle_number="MH14CD5678",
                license_number="DL-0420110149999",
                approval_status=ApprovalStatus.approved,
                last_lat=RIDER_LAT,
                last_lng=RIDER_LNG,
                is_online=False,
            )
        elif combo.rider_profile is not None:
            combo.rider_profile.is_online = False

        # Applicant rider whose verification is still under review — gives the
        # admin dashboard a real application to approve during the demo.
        applicant, created_applicant = _get_or_create_user(
            db, "applicant@digimess.app",
            full_name="Anand Applicant", phone="+919000000005",
            roles=UserRole.rider.value,
        )
        if created_applicant or applicant.rider_profile is None:
            applicant.rider_profile = RiderProfile(
                vehicle_type="bike",
                vehicle_number="MH12XY9090",
                license_number="DL-0420110145555",
                approval_status=ApprovalStatus.submitted,
                is_online=False,
            )

        db.flush()

        # Saved address for the customer.
        if not db.execute(
            select(Address).where(Address.user_id == customer.id)
        ).scalar_one_or_none():
            db.add(
                Address(
                    user_id=customer.id,
                    label="Home",
                    line1="Flat 4B, Shivaji Nagar",
                    lat=CUST_LAT,
                    lng=CUST_LNG,
                    is_default=True,
                )
            )

        # Mess + menu.
        mess = db.execute(
            select(Mess).where(Mess.owner_user_id == mess_owner.id)
        ).scalars().first()
        if mess is None:
            mess = Mess(
                owner_user_id=mess_owner.id,
                name="Khana Delivery Kitchen",
                description="Home-style thalis and comfort meals.",
                address_text="Shop 12, FC Road",
                lat=MESS_LAT,
                lng=MESS_LNG,
                is_open=True,
                delivery_fee_cents=2000,
            )
            db.add(mess)
            db.flush()
            for name, desc, price in [
                ("Veg Thali", "Dal, sabzi, rice, 3 rotis, salad", 12000),
                ("Non-Veg Thali", "Chicken curry, rice, 3 rotis, salad", 16000),
                ("Paneer Butter Masala", "With 2 butter naans", 18000),
                ("Curd Rice", "Comfort bowl with pickle", 9000),
                ("Gulab Jamun (2 pc)", "Warm dessert", 5000),
            ]:
                db.add(
                    MenuItem(
                        mess_id=mess.id, name=name, description=desc,
                        category="Meals", price_cents=price, is_available=True,
                    )
                )



        # Demo verification docs for applicant (mixed review states).
        if applicant.rider_profile and not db.execute(
            select(RiderDocument).where(RiderDocument.rider_id == applicant.id)
        ).scalars().first():
            now = utcnow()
            for doc_type, name, doc_status in [
                ("id_proof", "aadhaar_front.jpg", DocumentStatus.accepted),
                ("license", "DL_Front_Rahul.jpg", DocumentStatus.submitted),
                ("vehicle_rc", "vehicle_rc_front.jpg", DocumentStatus.submitted),
                ("bank_passbook", "bank_passbook.jpg", DocumentStatus.accepted),
            ]:
                db.add(RiderDocument(
                    rider_id=applicant.id,
                    doc_type=doc_type,
                    file_path=f"/dev/null/{doc_type}",
                    original_name=name,
                    content_type="image/jpeg",
                    size_bytes=2048,
                    status=doc_status,
                    uploaded_at=now,
                ))

        # Demo verification documents for the approved rider profile screen.
        if not db.execute(select(RiderDocument).where(RiderDocument.rider_id == rider.id)).scalars().first():
            now = utcnow()
            for doc_type, name in [
                ("license", "drivers_license.pdf"),
                ("vehicle_rc", "vehicle_rc.pdf"),
                ("insurance", "vehicle_insurance.pdf"),
                ("id_proof", "aadhaar.pdf"),
            ]:
                db.add(RiderDocument(
                    rider_id=rider.id,
                    doc_type=doc_type,
                    file_path=f"/dev/null/{doc_type}",
                    original_name=name,
                    content_type="application/pdf",
                    size_bytes=1024,
                    status=DocumentStatus.accepted,
                    uploaded_at=now,
                    expires_at=datetime(2026, 12, 31),
                ))

        from app.services import active_delivery_service, earnings_service, history_service, support_service, wallet_service, withdrawal_admin_service
        from app.models.support_ticket import SupportTicket
        support_service.seed_faqs(db)
        if mess and rider:
            history_service.seed_demo_history(db, rider.id, customer.id, mess.id)
            earnings_service.seed_earnings_demo(db, rider.id, customer.id, mess.id)
            wallet_service.seed_wallet_demo(db, rider.id)
            withdrawal_admin_service.seed_admin_withdrawals(db, rider.id)
            if settings.seed_pickup_delivery:
                active_delivery_service.seed_demo_pickup_delivery(db, rider.id, customer.id, mess.id)
            elif settings.seed_active_delivery:
                active_delivery_service.seed_demo_active_delivery(db, rider.id, customer.id, mess.id)
        rider_user = db.execute(select(User).where(User.email == "rider@digimess.app")).scalar_one_or_none()
        if rider_user and not db.execute(select(SupportTicket).where(SupportTicket.rider_id == rider_user.id)).scalars().first():
            db.add(SupportTicket(
                rider_id=rider_user.id,
                ticket_number="DM-8924",
                category="payout",
                topic="surge_adjustment",
                title="Surge adjustment",
                message="Surge multiplier was not applied correctly on order #4401 during peak dinner hours.",
                order_id=4401,
                status="in_review",
            ))

        db.commit()
    print("Seed complete. Demo password:", PASSWORD)


if __name__ == "__main__":
    seed()
