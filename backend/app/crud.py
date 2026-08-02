import uuid

from app.core.security import get_password_hash, verify_password
from app.models import Country, CountryCreate, User, UserCreate, UserUpdate


async def create_user(*, user_create: UserCreate) -> User:
    db_obj = User(
        email=user_create.email,
        is_active=user_create.is_active,
        is_superuser=user_create.is_superuser,
        full_name=user_create.full_name,
        hashed_password=get_password_hash(user_create.password),
    )
    await db_obj.insert()
    return db_obj


async def update_user(*, db_user: User, user_in: UserUpdate) -> User:
    user_data = user_in.model_dump(exclude_unset=True)
    if "password" in user_data:
        user_data["hashed_password"] = get_password_hash(user_data.pop("password"))
    if user_data:
        await db_user.set(user_data)
    return db_user


async def get_user_by_email(*, email: str) -> User | None:
    return await User.find_one(User.email == email)


# Dummy hash to use for timing attack prevention when user is not found
# This is an Argon2 hash of a random password, used to ensure constant-time comparison
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"


async def authenticate(*, email: str, password: str) -> User | None:
    db_user = await get_user_by_email(email=email)
    if not db_user:
        # Prevent timing attacks by running password verification even when user doesn't exist
        verify_password(password, DUMMY_HASH)
        return None
    verified, updated_password_hash = verify_password(password, db_user.hashed_password)
    if not verified:
        return None
    if updated_password_hash:
        await db_user.set({"hashed_password": updated_password_hash})
    return db_user


async def create_country(*, country_in: CountryCreate, owner_id: uuid.UUID) -> Country:
    db_country = Country(
        **country_in.model_dump(),
        owner_id=owner_id,
    )
    await db_country.insert()
    return db_country
