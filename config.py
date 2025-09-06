import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://root:deep026100@localhost/qr_attendance"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    QR_FOLDER = os.path.join(BASE_DIR, "static", "qrcodes")
    APP_NAME = "QR Library"
     
    # Operator password for override actions
    OPERATOR_PASSWORD = os.getenv("OPERATOR_PASSWORD", "stopface123")   
    