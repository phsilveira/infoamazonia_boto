from fastapi import APIRouter, Depends
from typing import Dict
from sqlalchemy.orm import Session
from database import get_db
from services.location import validate_brazilian_location, get_location_details
from models import Location
import schemas

router = APIRouter()

@router.post("/validate-location")
async def validate_location(location: schemas.LocationCreate):
    is_valid, corrected_name, region_type = await validate_brazilian_location(location.location_name)
    return {"is_valid": is_valid, "corrected_name": corrected_name, "region_type": region_type}

@router.post("/location-details")
async def get_location_info(location: schemas.LocationCreate, db: Session = Depends(get_db)):
    location_details = await get_location_details(location.location_name)
    
    # Save location to database
    db_location = Location(
        location_name=location_details["corrected_name"],
        latitude=location_details["latitude"],
        longitude=location_details["longitude"],
        user_id=location.user_id
    )
    db.add(db_location)
    db.commit()
    db.refresh(db_location)
    
    return location_details
