"""Authentication & registration logic (role-aware).

Customers self-register. Riders may register but are created ``pending`` and
cannot perform rider actions until approved — users never gain privileged
capability merely by choosing a role at signup. Role switching is limited to
roles already granted to the account.
"""
from __future__ import annotations

import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.services.otp_service import generate_otp, otp_matches
from app.models.auth_otp import LoginOtp
from app.models.base import utcnow
from app.models.enums import ApprovalStatus, UserRole
from app.models.mess import Mess
from app.models.user import RiderProfile, User
from app.schemas.auth import CustomerRegister, MessRegister, RiderRegister, Token


class AuthError(Exception):
    """Raised for registration/login failures (mapped to HTTP 400/401)."""


def _get_by_email(db: Session, email: str) -> User | None:
    return db.execute(
        select(User).where(User.email == email.lower())
    ).scalar_one_or_none()


def register_customer(db: Session, data: CustomerRegister) -> User:
    if _get_by_email(db, data.email):
        raise AuthError("An account with this email already exists")
    user = User(
        email=data.email.lower(),
        full_name=data.full_name,
        phone=data.phone,
        hashed_password=hash_password(data.password),
        roles=UserRole.customer.value,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def register_rider(db: Session, data: RiderRegister) -> User:
    existing = _get_by_email(db, data.email)
    if existing:
        # Allow an existing customer to also apply as a rider (adds the role,
        # still pending approval); block duplicate rider applications.
        if existing.has_role(UserRole.rider):
            raise AuthError("A rider account with this email already exists")
        existing.add_role(UserRole.rider)
        if data.phone:
            existing.phone = _normalize_phone(data.phone)
        user = existing
    else:
        user = User(
            email=data.email.lower(),
            full_name=data.full_name,
            phone=_normalize_phone(data.phone) if data.phone else None,
            hashed_password=hash_password(data.password),
            roles=UserRole.rider.value,
        )
        db.add(user)
        db.flush()

    user.rider_profile = RiderProfile(
        vehicle_type=data.vehicle_type,
        vehicle_number=data.vehicle_number,
        license_number=data.license_number,
        emergency_contact=data.emergency_contact or "",
        approval_status=ApprovalStatus.submitted,
    )
    db.commit()
    db.refresh(user)
    return user


def register_mess(db: Session, data: MessRegister) -> User:
    existing = _get_by_email(db, data.email)
    if existing:
        if existing.has_role(UserRole.mess):
            raise AuthError("A mess account with this email already exists")
        owned = db.execute(
            select(Mess).where(Mess.owner_user_id == existing.id)
        ).scalar_one_or_none()
        if owned is not None:
            raise AuthError("This account already owns a mess kitchen")
        existing.add_role(UserRole.mess)
        user = existing
    else:
        user = User(
            email=data.email.lower(),
            full_name=data.full_name,
            phone=data.phone,
            hashed_password=hash_password(data.password),
            roles=UserRole.mess.value,
        )
        db.add(user)
        db.flush()

    db.add(
        Mess(
            owner_user_id=user.id,
            name=data.mess_name,
            description=data.description,
            address_text=data.address_text,
            lat=data.lat,
            lng=data.lng,
            is_open=True,
        )
    )
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = _get_by_email(db, email)
    if user is None or not verify_password(password, user.hashed_password):
        raise AuthError("Incorrect email or password")
    if not user.is_active:
        raise AuthError("Account is disabled")
    return user


def issue_token(user: User, role: UserRole) -> Token:
    token = create_access_token(subject=user.id, role=role.value)
    return Token(
        access_token=token,
        role=role.value,
        roles=user.role_list,
    )


def login_as(db: Session, email: str, password: str, role: UserRole) -> tuple[User, Token]:
    user = authenticate(db, email, password)
    if not user.has_role(role):
        raise AuthError(f"This account is not authorized for the {role.value} role")
    if role == UserRole.rider and user.rider_profile is not None:
        user.rider_profile.is_online = user.rider_profile.is_online  # no-op, clarity
    return user, issue_token(user, role)


def switch_role(user: User, role_value: str) -> Token:
    try:
        role = UserRole(role_value)
    except ValueError:
        raise AuthError(f"Unknown role: {role_value}")
    if not user.has_role(role):
        raise AuthError(f"Account is not authorized for the {role.value} role")
    return issue_token(user, role)


def _normalize_phone(phone: str) -> str:
    """Normalize Indian mobiles to E.164 (+91XXXXXXXXXX)."""
    raw = phone.replace(" ", "").replace("-", "").strip()
    if not raw:
        return ""
    if raw.startswith("+") and raw[1:].isdigit():
        digits = raw[1:]
    else:
        digits = raw
    if digits.startswith("91") and len(digits) == 12 and digits.isdigit():
        return f"+{digits}"
    if digits.startswith("0") and len(digits) == 11 and digits.isdigit():
        digits = digits[1:]
    if len(digits) == 10 and digits.isdigit():
        return f"+91{digits}"
    return raw if raw.startswith("+") else phone.replace(" ", "").strip()


def _phone_lookup_variants(phone: str) -> list[str]:
    canonical = _normalize_phone(phone)
    variants: set[str] = set()
    if canonical:
        variants.add(canonical)
    raw = phone.replace(" ", "").replace("-", "").strip()
    if raw:
        variants.add(raw)
    if canonical.startswith("+91") and len(canonical) == 13:
        ten = canonical[3:]
        variants.update({ten, f"0{ten}", f"91{ten}"})
    return list(variants)


def request_customer_otp(db: Session, phone: str) -> str:
    """Create a login OTP for a phone number and return the code.

    In production the code would be sent by SMS and never returned. In dev the
    caller surfaces it so the flow is testable without an SMS gateway.
    """
    phone = _normalize_phone(phone)
    if not phone:
        raise AuthError("Phone number is required")
    code = generate_otp()
    otp = LoginOtp(
        phone=phone,
        code=code,
        expires_at=utcnow() + timedelta(minutes=settings.login_otp_expiry_minutes),
    )
    db.add(otp)
    db.commit()
    return code


def verify_customer_otp(
    db: Session, phone: str, code: str, full_name: str | None = None
) -> tuple[User, Token]:
    phone = _normalize_phone(phone)
    otp = db.execute(
        select(LoginOtp)
        .where(
            LoginOtp.phone == phone,
            LoginOtp.consumed.is_(False),
        )
        .order_by(LoginOtp.id.desc())
    ).scalars().first()

    if not otp_matches(code, otp.code if otp else None):
        raise AuthError("Incorrect verification code")
    if otp is not None and otp.expires_at < utcnow() and code.strip() != settings.default_otp:
        raise AuthError("Verification code has expired")

    if otp is not None:
        otp.consumed = True

    user = db.execute(select(User).where(User.phone == phone)).scalar_one_or_none()
    if user is None:
        # First-time phone sign-in creates a customer account.
        user = User(
            phone=phone,
            email=None,
            full_name=(full_name or "").strip() or "Khana Delivery Customer",
            hashed_password=hash_password(secrets.token_urlsafe(16)),
            roles=UserRole.customer.value,
        )
        db.add(user)
    elif not user.has_role(UserRole.customer):
        user.add_role(UserRole.customer)

    if full_name and full_name.strip() and user.full_name in ("", "Khana Delivery Customer"):
        user.full_name = full_name.strip()

    db.commit()
    db.refresh(user)
    return user, issue_token(user, UserRole.customer)



def _get_by_phone(db: Session, phone: str) -> User | None:
    variants = _phone_lookup_variants(phone)
    users = db.execute(select(User).where(User.phone.in_(variants))).scalars().all()
    if not users:
        return None
    riders = [u for u in users if u.has_role(UserRole.rider)]
    if riders:
        return riders[0]
    return users[0]


def request_rider_otp(db: Session, phone: str) -> str:
    phone = _normalize_phone(phone)
    if not phone:
        raise AuthError("Phone number is required")
    user = _get_by_phone(db, phone)
    if user is None or not user.has_role(UserRole.rider):
        raise AuthError("No delivery partner account found for this phone number")
    code = generate_otp()
    otp = LoginOtp(
        phone=phone,
        code=code,
        expires_at=utcnow() + timedelta(minutes=settings.login_otp_expiry_minutes),
    )
    db.add(otp)
    db.commit()
    return code


def verify_rider_otp(db: Session, phone: str, code: str) -> tuple[User, Token]:
    phone = _normalize_phone(phone)
    otp = db.execute(
        select(LoginOtp)
        .where(LoginOtp.phone == phone, LoginOtp.consumed.is_(False))
        .order_by(LoginOtp.id.desc())
    ).scalars().first()
    if not otp_matches(code, otp.code if otp else None):
        raise AuthError("Incorrect verification code")
    if otp is not None and otp.expires_at < utcnow() and code.strip() != settings.default_otp:
        raise AuthError("Verification code has expired")
    if otp is not None:
        otp.consumed = True
    user = _get_by_phone(db, phone)
    if user is None or not user.has_role(UserRole.rider):
        raise AuthError("No delivery partner account found for this phone number")
    if not user.is_active:
        raise AuthError("Account is disabled")
    db.commit()
    db.refresh(user)
    return user, issue_token(user, UserRole.rider)

def set_rider_online(db: Session, user: User, online: bool) -> None:
    profile = user.rider_profile
    if profile is None:
        raise AuthError("No rider profile")
    profile.is_online = online
    if online:
        profile.last_online_at = utcnow()
    db.commit()
