import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserBrief(ORM):
    id: uuid.UUID
    name: str
    email: str


class OrgMembershipOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    role: str


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    is_superuser: bool
    mfa_enabled: bool
    must_change_password: bool
    organizations: list[OrgMembershipOut]


class Ok(BaseModel):
    ok: bool = True


class Page(BaseModel):
    total: int


def me_out(user) -> MeOut:
    return MeOut(
        id=user.id,
        email=user.email,
        name=user.name,
        is_superuser=user.is_superuser,
        mfa_enabled=user.mfa_enabled,
        must_change_password=user.must_change_password,
        organizations=[
            OrgMembershipOut(id=m.org.id, name=m.org.name, slug=m.org.slug, role=m.role.value)
            for m in sorted(user.memberships, key=lambda m: m.org.name.lower())
        ],
    )


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None
