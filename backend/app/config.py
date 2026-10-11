import os

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://gamepulse:gamepulse@localhost:5432/gamepulse"
)

SYNTHETIC_NOTICE = (
    "This project uses synthetic data created for portfolio purposes and is "
    "not affiliated with Garena or Free Fire."
)

# Countries called out in the MENA market comparison (analytical framework only).
MENA_COUNTRIES = ["Morocco", "Saudi Arabia", "UAE", "Egypt", "Algeria", "Tunisia"]

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
