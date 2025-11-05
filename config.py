import os
import urllib
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- SQL Server Connection Config ---
DRIVER = os.getenv("SQL_DRIVER", "ODBC Driver 17 for SQL Server")
SERVER = os.getenv("SQL_SERVER", "LENOVO-LOQ\\MSSQL")  # your default server
DATABASE = os.getenv("SQL_DATABASE", "python")
TRUSTED_CONNECTION = os.getenv("SQL_TRUSTED_CONNECTION", "yes")

# Build connection string safely
connection_string = (
    f"DRIVER={{{DRIVER}}};"
    f"SERVER={SERVER};"
    f"DATABASE={DATABASE};"
    f"Trusted_Connection={TRUSTED_CONNECTION};"
)

# URL encode for SQLAlchemy
params = urllib.parse.quote_plus(connection_string)

# Final SQLAlchemy URI
SQLALCHEMY_DATABASE_URI = f"mssql+pyodbc:///?odbc_connect={params}"

# Other Config
SQLALCHEMY_TRACK_MODIFICATIONS = False
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "supersecretkey")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Instantiate db (to import in app.py)
db = SQLAlchemy()
