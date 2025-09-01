import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(BASE_DIR, 'library.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    QR_FOLDER = os.path.join(BASE_DIR, "static", "qrcodes")
    APP_NAME = "QR Library"
