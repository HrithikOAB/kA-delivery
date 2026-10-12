"""Seed the database with admin and partner accounts only.

Run with:  python -m app.seed
Idempotent: safe to run multiple times.

Demo credentials (password for all: ``password123``):
  * admin@kadelivery.app     — super admin
  * verifier@digimess.app    — partner-verification admin
  * ops@digimess.app         — operations admin
  * rider@digimess.app       — approved rider (delivery OTP in dev: 1212)
  * rider2@digimess.app      — second approved rider (for multi-rider tests)
  * applicant@digimess.app   — rider application under review
"""
from __future__ import annotations

from sqlalchemy import select

from app.config import settings
from app.core.security import hash_password
from app.database import SessionLocal
from app.models.enums import AdminRole, ApprovalStatus, DocumentStatus, UserRole
from app.models.rider_document import RiderDocument
from app.models.user import RiderProfile, User
from app.models.base import utcnow

PASSWORD = "password123"
RIDER_LAT, RIDER_LNG = 18.5250, 73.8500


def _admin_bootstrap_password() -> str:
    configured = settings.seed_admin_password.strip()
    if configured:
        return configured
    if settings.is_production:
        raise RuntimeError(
            "SEED_ADMIN_PASSWORD must be set to bootstrap the first admin account."
        )
    return PASSWORD


def seed_admin() -> None:
    """Create the super-admin account (idempotent). Used on first startup."""
    email = settings.seed_admin_email.strip().lower()
    if not email:
        raise RuntimeError("SEED_ADMIN_EMAIL must be set.")
    password = _admin_bootstrap_password()

    with SessionLocal() as db:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            user = User(
                email=email,
                full_name="Platform Admin",
                phone="+919000000010",
                hashed_password=hash_password(password),
                roles=UserRole.admin.value,
            )
            db.add(user)
            db.flush()
        user.admin_role = AdminRole.super_admin
        if not user.has_role(UserRole.admin):
            user.add_role(UserRole.admin)
        db.commit()


def _get_or_create_user(db, email: str, **kwargs) -> tuple[User, bool]:
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user:
        return user, False
    user = User(email=email, hashed_password=hash_password(PASSWORD), **kwargs)
    db.add(user)
    db.flush()
    return user, True


def _ensure_rider_profile(
    db,
    user: User,
    *,
    approval_status: ApprovalStatus,
    is_online: bool = False,
    partner_code: str | None = None,
) -> None:
    if user.rider_profile is None:
        user.rider_profile = RiderProfile(
            vehicle_type="scooter",
            vehicle_number="KA-01-EQ-9421",
            license_number="DL-0420110149646",
            approval_status=approval_status,
            last_lat=RIDER_LAT if is_online else None,
            last_lng=RIDER_LNG if is_online else None,
            is_online=is_online,
            partner_code=partner_code,
            phone_verified=True,
            bank_name="HDFC Bank",
            ifsc_code="HDFC0000128",
            bank_account_masked="8839",
        )
    else:
        rp = user.rider_profile
        rp.approval_status = approval_status
        rp.is_online = is_online
        if is_online:
            rp.last_lat = rp.last_lat if rp.last_lat is not None else RIDER_LAT
            rp.last_lng = rp.last_lng if rp.last_lng is not None else RIDER_LNG
        if partner_code:
            rp.partner_code = partner_code


def seed() -> None:
    seed_admin()
    with SessionLocal() as db:
        super_admin = db.execute(
            select(User).where(User.email == settings.seed_admin_email.strip().lower())
        ).scalar_one()
        super_admin.full_name = "Aditi Admin"

        verifier, _ = _get_or_create_user(
            db,
            "verifier@digimess.app",
            full_name="Vikram Verifier",
            phone="+919000000011",
            roles=UserRole.admin.value,
        )
        verifier.admin_role = AdminRole.partner_verification

        ops, _ = _get_or_create_user(
            db,
            "ops@digimess.app",
            full_name="Omar Ops",
            phone="+919000000012",
            roles=UserRole.admin.value,
        )
        ops.admin_role = AdminRole.operations

        rider, _ = _get_or_create_user(
            db,
            "rider@digimess.app",
            full_name="Rahul Sharma",
            phone="+91 98765 43210",
            roles=UserRole.rider.value,
        )
        _ensure_rider_profile(
            db,
            rider,
            approval_status=ApprovalStatus.approved,
            is_online=True,
            partner_code="DM-PARTNER-7721",
        )

        rider2, _ = _get_or_create_user(
            db,
            "rider2@digimess.app",
            full_name="Ravi Rider",
            phone="+919000000020",
            roles=UserRole.rider.value,
        )
        _ensure_rider_profile(
            db,
            rider2,
            approval_status=ApprovalStatus.approved,
            is_online=False,
            partner_code="DM-PARTNER-7722",
        )

        applicant, created_applicant = _get_or_create_user(
            db,
            "applicant@digimess.app",
            full_name="Anand Applicant",
            phone="+919000000005",
            roles=UserRole.rider.value,
        )
        _ensure_rider_profile(db, applicant, approval_status=ApprovalStatus.submitted, is_online=False)

        db.flush()

        if created_applicant and not db.execute(
            select(RiderDocument).where(RiderDocument.rider_id == applicant.id)
        ).scalars().first():
            now = utcnow()
            for doc_type, name, doc_status in [
                ("id_proof", "aadhaar_front.jpg", DocumentStatus.accepted),
                ("license", "DL_Front.jpg", DocumentStatus.submitted),
                ("vehicle_rc", "vehicle_rc_front.jpg", DocumentStatus.submitted),
                ("bank_passbook", "bank_passbook.jpg", DocumentStatus.accepted),
            ]:
                db.add(
                    RiderDocument(
                        rider_id=applicant.id,
                        doc_type=doc_type,
                        file_path=f"/dev/null/{doc_type}",
                        original_name=name,
                        content_type="image/jpeg",
                        size_bytes=2048,
                        status=doc_status,
                        uploaded_at=now,
                    )
                )

        db.commit()
    print("Seed complete. Demo password:", PASSWORD)


if __name__ == "__main__":
    seed()
