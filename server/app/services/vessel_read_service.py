from sqlalchemy.orm import Session

from app.models.vessel import Vessel
from app.repositories.fee_config_repository import fee_config_repo
from app.schemas.vessel import ApplicableFeeRead, VesselRead


def vessel_to_read(db: Session, vessel: Vessel) -> VesselRead:
    """Build VesselRead with nested type and first active fee config for that type."""
    base = VesselRead.model_validate(vessel)
    fee_obj = None
    if vessel.vessel_type_id:
        confs = fee_config_repo.get_by_vessel_type(db, vessel.vessel_type_id)
        if confs:
            fee_obj = ApplicableFeeRead.model_validate(confs[0])
    return base.model_copy(update={'applicable_fee': fee_obj})
