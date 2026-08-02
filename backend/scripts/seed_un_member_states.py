#!/usr/bin/env python3
import argparse
import asyncio
import re
import sys
import unicodedata
import uuid
from html import unescape
from pathlib import Path

import httpx
from beanie import init_beanie
from pymongo import AsyncMongoClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.models import Country, User  # noqa: E402

UN_MEMBER_STATES_URL = "https://www.un.org/es/about-us/member-states"


def _log(message: str) -> None:
    sys.stdout.write(f"{message}\n")


def _strip_html_tags(value: str) -> str:
    clean = re.sub(r"<[^>]+>", " ", value)
    clean = unescape(clean)
    return re.sub(r"\s+", " ", clean).strip()


def _simplify_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


KNOWN_ALIASES: dict[str, str] = {
    "bahrein": "Bahrein",
    "bosnia and herzegovina": "Bosnia y Herzegovina",
    "cape verde": "Cabo Verde",
    "czech republic": "Chequia",
    "czechia": "Chequia",
    "east timor": "Timor-Leste",
    "ivory coast": "Côte D'Ivoire",
    "lao peoples democratic republic": "República Democrática Popular Lao",
    "micronesia": "Micronesia (Estados Federados de)",
    "moldova": "República de Moldova",
    "netherlands": "Países Bajos (Reino de los)",
    "north korea": "República Popular Democrática de Corea",
    "russia": "Federación de Rusia",
    "russian federation": "Federación de Rusia",
    "south korea": "República de Corea",
    "syria": "República Árabe Siria",
    "tanzania": "República Unida de Tanzanía",
    "turkey": "Türkiye",
    "united kingdom": "Reino Unido de Gran Bretaña e Irlanda del Norte",
    "united states": "Estados Unidos de América",
    "vatican city": "Santa Sede",
    "venezuela": "Venezuela (República Bolivariana de)",
    "vietnam": "Viet Nam",
}


def _extract_member_states_from_html(html: str) -> list[str]:
    sections = re.findall(
        r"<h2[^>]*>(?P<title>.*?)</h2>(?P<body>.*?)(?=<h2[^>]*>|$)",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    states: list[str] = []
    for title_html, body_html in sections:
        title = _strip_html_tags(title_html)
        body = _strip_html_tags(body_html)
        if not title:
            continue
        if "Fecha de admisión" not in body:
            continue
        states.append(title)

    unique_states: list[str] = []
    seen: set[str] = set()
    for state in states:
        key = state.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique_states.append(state)
    return unique_states


async def _fetch_un_member_states() -> list[str]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(UN_MEMBER_STATES_URL)
        response.raise_for_status()
    return _extract_member_states_from_html(response.text)


async def seed_un_member_states(
    owner_email: str | None,
    owner_id: str | None,
    dry_run: bool,
    update_existing: bool,
) -> None:
    client = AsyncMongoClient(settings.MONGODB_URL)
    try:
        database = client[settings.MONGODB_DB]
        await init_beanie(database=database, document_models=[User, Country])

        owner_uuid: uuid.UUID | None = None
        if owner_id:
            owner_uuid = uuid.UUID(owner_id)
            owner = await User.get(owner_uuid)
            if not owner:
                raise ValueError(f"No existe usuario con owner_id={owner_id}")
        else:
            selected_email = owner_email or str(settings.FIRST_SUPERUSER)
            owner = await User.find_one(User.email == selected_email)
            if not owner:
                raise ValueError(
                    "No se encontró un usuario para asignar owner_id. "
                    "Usa --owner-id o --owner-email con un usuario existente."
                )
            owner_uuid = owner.id

        if owner_uuid is None:
            raise ValueError("No fue posible resolver owner_id")

        member_states = await _fetch_un_member_states()
        if not member_states:
            raise ValueError("No se pudieron extraer países desde la web de la ONU")

        un_by_simplified = {_simplify_name(name): name for name in member_states}
        for alias, official_name in KNOWN_ALIASES.items():
            if official_name in member_states:
                un_by_simplified[_simplify_name(alias)] = official_name

        existing_countries = await Country.find_all().to_list()
        existing_by_name = {
            country.country_name.casefold() for country in existing_countries
        }

        to_insert = [
            name for name in member_states if name.casefold() not in existing_by_name
        ]
        to_update: list[tuple[Country, str]] = []
        if update_existing:
            existing_casefold_to_id = {
                country.country_name.casefold(): country.id
                for country in existing_countries
            }
            for country in existing_countries:
                official_name = un_by_simplified.get(
                    _simplify_name(country.country_name)
                )
                if not official_name:
                    continue
                if official_name == country.country_name:
                    continue
                owner_of_official = existing_casefold_to_id.get(
                    official_name.casefold()
                )
                if owner_of_official and owner_of_official != country.id:
                    continue
                to_update.append((country, official_name))

        if dry_run:
            _log(f"Detectados en web ONU: {len(member_states)}")
            _log(f"Ya existentes en DB: {len(existing_countries)}")
            _log(f"Nuevos a insertar: {len(to_insert)}")
            if update_existing:
                _log(f"Registros a renombrar: {len(to_update)}")
            return

        updated = 0
        for country, official_name in to_update:
            await country.set({"country_name": official_name})
            updated += 1

        inserted = 0
        for country_name in to_insert:
            country = Country(country_name=country_name, owner_id=owner_uuid)
            await country.insert()
            inserted += 1

        _log(f"Detectados en web ONU: {len(member_states)}")
        _log(f"Insertados: {inserted}")
        if update_existing:
            _log(f"Renombrados: {updated}")
        _log(f"Omitidos por duplicado: {len(member_states) - inserted}")
    finally:
        await client.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inserta en MongoDB los países miembros de la ONU."
    )
    parser.add_argument(
        "--owner-email",
        help="Email del usuario propietario de los registros (opcional).",
    )
    parser.add_argument(
        "--owner-id",
        help="UUID del usuario propietario de los registros (opcional).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra cuántos países insertaría sin modificar la base de datos.",
    )
    parser.add_argument(
        "--update-existing",
        action="store_true",
        help="Renombra países existentes para alinearlos al nombre oficial ONU.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(
        seed_un_member_states(
            owner_email=args.owner_email,
            owner_id=args.owner_id,
            dry_run=args.dry_run,
            update_existing=args.update_existing,
        )
    )


if __name__ == "__main__":
    main()
