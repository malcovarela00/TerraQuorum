import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser
from app.models import (
    CountriesPublic,
    Country,
    CountryBulkCreate,
    CountryBulkCreatePublic,
    CountryCreate,
    CountryMapDataResponse,
    CountryMapPoint,
    CountryPublic,
    CountryUpdate,
    Message,
)

router = APIRouter(prefix="/countries", tags=["countries"])


# Suffixes used to mark internal metadata keys inside ``custom_data``. Any
# key ending with one of these is hidden from the map and tables; they hold
# auxiliary content such as stance rationales or research metadata.
_INTERNAL_DATA_SUFFIXES: tuple[str, ...] = ("__rationale", "__meta")


def _is_internal_data_key(key: str) -> bool:
    return any(key.endswith(suffix) for suffix in _INTERNAL_DATA_SUFFIXES)


def _strip_internal_data(custom_data: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in custom_data.items()
        if not _is_internal_data_key(key)
    }


def _normalize_country_name(name: str) -> str:
    return name.strip().casefold()


@router.get("/map-data", response_model=CountryMapDataResponse)
async def get_map_data(current_user: CurrentUser) -> Any:
    """
    Return all countries with custom_data and ISO codes for the map visualization.
    """
    if current_user.is_superuser:
        countries = await Country.find_all().to_list()
    else:
        countries = await Country.find(Country.owner_id == current_user.id).to_list()

    available_keys: set[str] = set()
    points: list[CountryMapPoint] = []

    for country in countries:
        cd = country.custom_data or {}
        public_data = _strip_internal_data(cd)
        available_keys.update(public_data.keys())
        points.append(
            CountryMapPoint(
                country_name=country.country_name,
                alpha_2=country.alpha_2,
                iso_numeric=country.iso_numeric,
                custom_data=public_data,
            )
        )

    return CountryMapDataResponse(
        data=points,
        available_keys=sorted(available_keys),
    )


@router.get("/", response_model=CountriesPublic)
async def read_countries(
    current_user: CurrentUser, skip: int = 0, limit: int = 100
) -> Any:
    """
    Retrieve countries.
    """

    if current_user.is_superuser:
        count = await Country.find().count()
        countries = (
            await Country.find().sort("-created_at").skip(skip).limit(limit).to_list()
        )
    else:
        count = await Country.find(Country.owner_id == current_user.id).count()
        countries = (
            await Country.find(Country.owner_id == current_user.id)
            .sort("-created_at")
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    return CountriesPublic(
        data=[
            CountryPublic.model_validate(country, from_attributes=True)
            for country in countries
        ],
        count=count,
    )


@router.get("/{id}", response_model=CountryPublic)
async def read_country(current_user: CurrentUser, id: uuid.UUID) -> Any:
    """
    Get country by ID.
    """
    country = await Country.get(id)
    if not country:
        raise HTTPException(status_code=404, detail="Country not found")
    if not current_user.is_superuser and (country.owner_id != current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return country


@router.post("/", response_model=CountryPublic)
async def create_country(
    *, current_user: CurrentUser, country_in: CountryCreate
) -> Any:
    """
    Create new country.
    """
    country = Country(**country_in.model_dump(), owner_id=current_user.id)
    await country.insert()
    return country


@router.post("/bulk", response_model=CountryBulkCreatePublic)
async def create_countries_bulk(
    *, current_user: CurrentUser, countries_in: CountryBulkCreate
) -> Any:
    """
    Create multiple countries and skip entries already present for the user.
    """
    existing_countries = await Country.find(
        Country.owner_id == current_user.id
    ).to_list()
    existing_alpha_2 = {
        country.alpha_2 for country in existing_countries if country.alpha_2
    }
    existing_iso_numeric = {
        country.iso_numeric for country in existing_countries if country.iso_numeric
    }
    existing_names_without_codes = {
        _normalize_country_name(country.country_name)
        for country in existing_countries
        if not country.alpha_2 and not country.iso_numeric
    }

    created: list[Country] = []
    skipped: list[CountryCreate] = []

    for country_in in countries_in.countries:
        has_duplicate_alpha_2 = (
            country_in.alpha_2 is not None and country_in.alpha_2 in existing_alpha_2
        )
        has_duplicate_iso_numeric = (
            country_in.iso_numeric is not None
            and country_in.iso_numeric in existing_iso_numeric
        )
        has_duplicate_name_without_codes = (
            country_in.alpha_2 is None
            and country_in.iso_numeric is None
            and _normalize_country_name(country_in.country_name)
            in existing_names_without_codes
        )
        if (
            has_duplicate_alpha_2
            or has_duplicate_iso_numeric
            or has_duplicate_name_without_codes
        ):
            skipped.append(country_in)
            continue

        country = Country(
            **country_in.model_dump(),
            owner_id=current_user.id,
        )
        await country.insert()
        created.append(country)

        if country.alpha_2:
            existing_alpha_2.add(country.alpha_2)
        if country.iso_numeric:
            existing_iso_numeric.add(country.iso_numeric)
        if not country.alpha_2 and not country.iso_numeric:
            existing_names_without_codes.add(
                _normalize_country_name(country.country_name)
            )

    return CountryBulkCreatePublic(
        created=[
            CountryPublic.model_validate(country, from_attributes=True)
            for country in created
        ],
        skipped=skipped,
    )


@router.put("/{id}", response_model=CountryPublic)
async def update_country(
    *,
    current_user: CurrentUser,
    id: uuid.UUID,
    country_in: CountryUpdate,
) -> Any:
    """
    Update a country.
    """
    country = await Country.get(id)
    if not country:
        raise HTTPException(status_code=404, detail="Country not found")
    if not current_user.is_superuser and (country.owner_id != current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    update_dict = country_in.model_dump(exclude_unset=True)
    if update_dict:
        await country.set(update_dict)
    return country


@router.delete("/{id}")
async def delete_country(current_user: CurrentUser, id: uuid.UUID) -> Message:
    """
    Delete a country.
    """
    country = await Country.get(id)
    if not country:
        raise HTTPException(status_code=404, detail="Country not found")
    if not current_user.is_superuser and (country.owner_id != current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    await country.delete()
    return Message(message="Country deleted successfully")
