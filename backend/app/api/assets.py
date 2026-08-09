from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.database.session import get_db
from app.models.core import Asset, User
from app.schemas.core import AssetCreate, AssetUpdate
from app.tenancy import current_organization

router = APIRouter(prefix='/assets', tags=['assets'])


@router.post('', status_code=201)
def create_asset(payload: AssetCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = current_organization(db, user)
    asset = Asset(organization_id=org.id, name=payload.name, asset_type=payload.asset_type, serial_number=payload.serial_number, notes=payload.notes)
    db.add(asset); db.commit(); db.refresh(asset); return asset


@router.get('')
def list_assets(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = current_organization(db, user)
    return db.query(Asset).filter(Asset.organization_id == org.id).order_by(Asset.created_at.desc()).all()


@router.patch('/{asset_id}')
def update_asset(asset_id: int, payload: AssetUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = current_organization(db, user)
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.organization_id == org.id).first()
    if asset is None: raise HTTPException(status_code=404, detail='Asset not found')
    if payload.status is not None: asset.status = payload.status
    if payload.notes is not None: asset.notes = payload.notes
    db.commit(); db.refresh(asset); return asset
