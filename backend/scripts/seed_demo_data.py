#!/usr/bin/env python3
# pylint: disable=import-error,wrong-import-position
import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from beanie import init_beanie
from pymongo import AsyncMongoClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.models import Country, User  # noqa: E402

DEMO_SOURCE = "TerraQuorum demo seed"

DEMO_COUNTRIES: list[dict[str, Any]] = [
    {
        "country_name": "Argentina",
        "alpha_2": "AR",
        "iso_numeric": "032",
        "custom_data": {
            "region": "América del Sur",
            "population_millions": 46.2,
            "gdp_per_capita_usd": 13730,
            "life_expectancy_years": 75.4,
            "un_voting_group": "G77 + China",
            "demo_summary": "País federal sudamericano con peso agrícola, energético y diplomático regional.",
        },
    },
    {
        "country_name": "Brasil",
        "alpha_2": "BR",
        "iso_numeric": "076",
        "custom_data": {
            "region": "América del Sur",
            "population_millions": 203.1,
            "gdp_per_capita_usd": 10043,
            "life_expectancy_years": 75.9,
            "un_voting_group": "G77 + China",
            "demo_summary": "Mayor economía latinoamericana y actor central en clima, biodiversidad y cooperación sur-sur.",
        },
    },
    {
        "country_name": "España",
        "alpha_2": "ES",
        "iso_numeric": "724",
        "custom_data": {
            "region": "Europa Occidental",
            "population_millions": 48.6,
            "gdp_per_capita_usd": 32677,
            "life_expectancy_years": 83.2,
            "un_voting_group": "Unión Europea",
            "demo_summary": "Estado miembro de la UE con vínculos diplomáticos fuertes con Europa, América Latina y el Mediterráneo.",
        },
    },
    {
        "country_name": "India",
        "alpha_2": "IN",
        "iso_numeric": "356",
        "custom_data": {
            "region": "Asia Meridional",
            "population_millions": 1428.6,
            "gdp_per_capita_usd": 2485,
            "life_expectancy_years": 67.7,
            "un_voting_group": "G77 + China",
            "demo_summary": "Potencia demográfica y tecnológica con papel creciente en gobernanza global.",
        },
    },
    {
        "country_name": "Kenia",
        "alpha_2": "KE",
        "iso_numeric": "404",
        "custom_data": {
            "region": "África Oriental",
            "population_millions": 55.1,
            "gdp_per_capita_usd": 1950,
            "life_expectancy_years": 61.4,
            "un_voting_group": "Grupo Africano",
            "demo_summary": "Hub diplomático regional y sede de importantes organismos de Naciones Unidas en África.",
        },
    },
]


def _log(message: str) -> None:
    sys.stdout.write(f"{message}\n")


def _demo_payload(country: dict[str, Any]) -> dict[str, Any]:
    custom_data = dict(country["custom_data"])
    custom_data["demo_data"] = True
    custom_data["demo_source"] = DEMO_SOURCE
    return {
        "country_name": country["country_name"],
        "alpha_2": country["alpha_2"],
        "iso_numeric": country["iso_numeric"],
        "custom_data": custom_data,
    }


async def seed_demo_data(*, dry_run: bool, reset_demo: bool) -> None:
    client = AsyncMongoClient(settings.MONGODB_URL)
    try:
        database = client[settings.MONGODB_DB]
        await init_beanie(database=database, document_models=[User, Country])

        owner = await User.find_one(User.email == settings.FIRST_SUPERUSER)
        if not owner:
            raise ValueError(
                "No existe el superusuario inicial. Ejecuta primero el prestart "
                "o crea el usuario definido en FIRST_SUPERUSER."
            )

        inserted = 0
        updated = 0
        reset = 0

        if reset_demo:
            demo_countries = await Country.find(
                {"custom_data.demo_source": DEMO_SOURCE}
            ).to_list()
            reset = len(demo_countries)
            if not dry_run:
                for country in demo_countries:
                    await country.delete()

        for raw_country in DEMO_COUNTRIES:
            payload = _demo_payload(raw_country)
            existing = await Country.find_one(
                Country.country_name == payload["country_name"]
            )
            if existing:
                updated += 1
                if not dry_run:
                    await existing.set(
                        {
                            "alpha_2": payload["alpha_2"],
                            "iso_numeric": payload["iso_numeric"],
                            "custom_data": {
                                **existing.custom_data,
                                **payload["custom_data"],
                            },
                        }
                    )
                continue

            inserted += 1
            if not dry_run:
                country = Country(owner_id=owner.id, **payload)
                await country.insert()

        prefix = "[dry-run] " if dry_run else ""
        _log(f"{prefix}Demo countries configured: {len(DEMO_COUNTRIES)}")
        _log(f"{prefix}Inserted: {inserted}")
        _log(f"{prefix}Updated: {updated}")
        if reset_demo:
            _log(f"{prefix}Deleted before seeding: {reset}")
    finally:
        await client.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed a small offline demo dataset for TerraQuorum."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be inserted or updated without modifying MongoDB.",
    )
    parser.add_argument(
        "--reset-demo",
        action="store_true",
        help="Delete previously seeded demo rows before inserting the demo dataset.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(seed_demo_data(dry_run=args.dry_run, reset_demo=args.reset_demo))


if __name__ == "__main__":
    main()
