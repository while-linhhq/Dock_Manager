from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.fee import (
    FeeConfigCreate,
    FeeConfigUpdate,
    FeeConfigRead,
    _validate_fee_scope,
    _validate_penalty_fields,
)
from app.repositories.fee_config_repository import fee_config_repo
from app.services.ship_invoice_backfill_service import (
    fee_backfill_target,
    fee_config_triggers_backfill,
    run_vessel_backfill_task,
    run_vessel_type_backfill_task,
    should_backfill_after_fee_update,
)

router = APIRouter()


def _schedule_fee_vessel_backfill(background_tasks: BackgroundTasks, vessel_id: int) -> None:
    background_tasks.add_task(run_vessel_backfill_task, vessel_id)


def _schedule_fee_backfill(background_tasks: BackgroundTasks, fee) -> None:
    target = fee_backfill_target(fee)
    if target is None:
        return
    scope, scope_id = target
    task = run_vessel_backfill_task if scope == 'vessel' else run_vessel_type_backfill_task
    background_tasks.add_task(task, scope_id)


@router.get('/', response_model=List[FeeConfigRead])
def list_fee_configs(
    active_only: bool = False,
    vessel_type_id: Optional[int] = None,
    vessel_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    if vessel_id:
        return fee_config_repo.get_by_vessel(db, vessel_id, active_only=active_only)
    if vessel_type_id:
        return fee_config_repo.get_by_vessel_type(db, vessel_type_id)
    return fee_config_repo.get_all(db, active_only=active_only)


@router.get('/{fee_id}', response_model=FeeConfigRead)
def get_fee_config(fee_id: int, db: Session = Depends(get_db)):
    obj = fee_config_repo.get(db, fee_id)
    if not obj:
        raise HTTPException(status_code=404, detail='Fee config not found')
    return obj


@router.post('/', response_model=FeeConfigRead, status_code=201)
def create_fee_config(
    data: FeeConfigCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    created = fee_config_repo.create(db, data.model_dump())
    if fee_config_triggers_backfill(created):
        _schedule_fee_backfill(background_tasks, created)
    return created


@router.put('/{fee_id}', response_model=FeeConfigRead)
def update_fee_config(
    fee_id: int,
    data: FeeConfigUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    before = fee_config_repo.get(db, fee_id)
    if not before:
        raise HTTPException(status_code=404, detail='Fee config not found')

    patch = data.model_dump(exclude_unset=True)
    try:
        _validate_fee_scope(
            vessel_id=patch.get('vessel_id', before.vessel_id),
            vessel_type_id=patch.get('vessel_type_id', before.vessel_type_id),
        )
        _validate_penalty_fields(
            berth_limit_count=patch.get('berth_limit_count', before.berth_limit_count),
            berth_limit_unit=patch.get('berth_limit_unit', before.berth_limit_unit),
            over_limit_penalty_amount=patch.get(
                'over_limit_penalty_amount',
                before.over_limit_penalty_amount,
            ),
            outside_hours_penalty_amount=patch.get(
                'outside_hours_penalty_amount',
                before.outside_hours_penalty_amount,
            ),
            operating_hours=patch.get('operating_hours', before.operating_hours),
            max_berth_duration_minutes=patch.get(
                'max_berth_duration_minutes',
                before.max_berth_duration_minutes,
            ),
            over_duration_penalty_amount=patch.get(
                'over_duration_penalty_amount',
                before.over_duration_penalty_amount,
            ),
            outside_hours_penalty_per_hour=patch.get(
                'outside_hours_penalty_per_hour',
                before.outside_hours_penalty_per_hour,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    updated = fee_config_repo.update(db, fee_id, patch)
    if not updated:
        raise HTTPException(status_code=404, detail='Fee config not found')

    if should_backfill_after_fee_update(before, updated):
        _schedule_fee_backfill(background_tasks, updated)

    return updated


@router.delete('/{fee_id}', status_code=204)
def delete_fee_config(fee_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Hard-delete the row. Invoice line items keep amounts; fee_config_id is set NULL (DB FK)."""
    if not fee_config_repo.delete(db, fee_id):
        raise HTTPException(status_code=404, detail='Fee config not found')
