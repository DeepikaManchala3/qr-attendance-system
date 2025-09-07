import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
<<<<<<< HEAD
        "mysql+pymysql://root:deep026100@localhost/qr_attendance2"
=======
        "mysql+pymysql://root:deep026100@localhost/qr_attendance"
>>>>>>> 7f6fb89d4a7392a1390e4de1c6994760096a92fd
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    QR_FOLDER = os.path.join(BASE_DIR, "static", "qrcodes")
    APP_NAME = "QR Library"
     
    # Operator password for override actions
    OPERATOR_PASSWORD = os.getenv("OPERATOR_PASSWORD", "stopface123")   
    