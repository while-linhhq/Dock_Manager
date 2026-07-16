from sqlalchemy.orm import Session

from app.models.vessel import Vessel
from app.repositories.fee_config_repository import fee_config_repo
from app.schemas.vessel import ApplicableFeeRead, VesselRead
from app.services.fee_resolution_service import resolve_billable_fees
from app.services.vessel_visual_reference_service import count_visual_references_by_ship_ids


def vessel_to_read(
    db: Session,
    vessel: Vessel,
    *,
    visual_reference_counts: dict[str, int] | None = None,
) -> VesselRead:
    """Build VesselRead with nested type and first active fee config for that type."""
    base = VesselRead.model_validate(vessel)
    fee_obj = None
    confs = resolve_billable_fees(db, vessel)
    if confs:
        fee_obj = ApplicableFeeRead.model_validate(confs[0])

    visual_count = 0
    if visual_reference_counts is not None:
        visual_count = int(visual_reference_counts.get(str(vessel.ship_id), 0))

    return base.model_copy(
        update={
            'applicable_fee': fee_obj,
            'visual_reference_count': visual_count,
        }
    )


def vessels_to_read(db: Session, vessels: list[Vessel]) -> list[VesselRead]:
    ship_ids = [str(v.ship_id) for v in vessels]
    counts = count_visual_references_by_ship_ids(ship_ids)
    return [
        vessel_to_read(db, vessel, visual_reference_counts=counts)
        for vessel in vessels
    ]
