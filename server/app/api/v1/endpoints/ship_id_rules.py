from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.repositories.ship_id_rule_repository import ship_id_rule_repo
from app.schemas.ship_id_rules import (
    BlacklistCreate,
    BlacklistRead,
    ConvertMapCreate,
    ConvertMapRead,
    ConvertMapUpdate,
    PatternCreate,
    PatternRead,
    PatternUpdate,
    PrefixConvertCreate,
    PrefixConvertRead,
    PrefixConvertUpdate,
)

router = APIRouter()


@router.get('/patterns', response_model=list[PatternRead])
def list_patterns(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return ship_id_rule_repo.get_all_patterns(db)


@router.post('/patterns', response_model=PatternRead, status_code=201)
def create_pattern(body: PatternCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return ship_id_rule_repo.create_pattern(db, body.model_dump())


@router.put('/patterns/{pattern_id}', response_model=PatternRead)
def update_pattern(
    pattern_id: int,
    body: PatternUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    result = ship_id_rule_repo.update_pattern(db, pattern_id, body.model_dump(exclude_none=True))
    if result is None:
        raise HTTPException(status_code=404, detail='Pattern not found')
    return result


@router.delete('/patterns/{pattern_id}', status_code=204)
def delete_pattern(pattern_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if not ship_id_rule_repo.delete_pattern(db, pattern_id):
        raise HTTPException(status_code=404, detail='Pattern not found')


@router.get('/blacklist', response_model=list[BlacklistRead])
def list_blacklist(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return ship_id_rule_repo.get_all_blacklist(db)


@router.post('/blacklist', response_model=BlacklistRead, status_code=201)
def create_blacklist(body: BlacklistCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    try:
        return ship_id_rule_repo.create_blacklist(db, body.model_dump())
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail='Value already in blacklist') from exc


@router.delete('/blacklist/{entry_id}', status_code=204)
def delete_blacklist(entry_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if not ship_id_rule_repo.delete_blacklist(db, entry_id):
        raise HTTPException(status_code=404, detail='Blacklist entry not found')


@router.get('/convert-map', response_model=list[ConvertMapRead])
def list_convert_map(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return ship_id_rule_repo.get_all_convert_map(db)


@router.post('/convert-map', response_model=ConvertMapRead, status_code=201)
def create_convert_map(
    body: ConvertMapCreate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    try:
        return ship_id_rule_repo.create_convert_map(db, body.model_dump())
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail='wrong_value already in convert map') from exc


@router.put('/convert-map/{entry_id}', response_model=ConvertMapRead)
def update_convert_map(
    entry_id: int,
    body: ConvertMapUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    result = ship_id_rule_repo.update_convert_map(db, entry_id, body.model_dump(exclude_none=True))
    if result is None:
        raise HTTPException(status_code=404, detail='Convert map entry not found')
    return result


@router.delete('/convert-map/{entry_id}', status_code=204)
def delete_convert_map(entry_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if not ship_id_rule_repo.delete_convert_map(db, entry_id):
        raise HTTPException(status_code=404, detail='Convert map entry not found')


@router.get('/prefix-convert', response_model=list[PrefixConvertRead])
def list_prefix_convert(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return ship_id_rule_repo.get_all_prefix_convert(db)


@router.post('/prefix-convert', response_model=PrefixConvertRead, status_code=201)
def create_prefix_convert(
    body: PrefixConvertCreate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    try:
        return ship_id_rule_repo.create_prefix_convert(db, body.model_dump())
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail='from_prefix already in prefix convert map') from exc


@router.put('/prefix-convert/{entry_id}', response_model=PrefixConvertRead)
def update_prefix_convert(
    entry_id: int,
    body: PrefixConvertUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    result = ship_id_rule_repo.update_prefix_convert(db, entry_id, body.model_dump(exclude_none=True))
    if result is None:
        raise HTTPException(status_code=404, detail='Prefix convert entry not found')
    return result


@router.delete('/prefix-convert/{entry_id}', status_code=204)
def delete_prefix_convert(entry_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if not ship_id_rule_repo.delete_prefix_convert(db, entry_id):
        raise HTTPException(status_code=404, detail='Prefix convert entry not found')


@router.post('/reload', status_code=200)
def force_reload(db: Session = Depends(get_db), _=Depends(get_current_user)):
    from app.services.ai.ship_id_rule_engine import get_rule_engine

    engine = get_rule_engine()
    reloaded = engine.reload(db)
    return {'reloaded': reloaded}
