from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token
from flask_sqlalchemy import SQLAlchemy


app = Flask(__name__)
CORS(app, origins=["http://localhost:5173"])

app.config["JWT_SECRET_KEY"] = "supersecretkey"
jwt = JWTManager(app)


app.config['SQLALCHEMY_DATABASE_URI'] = (
    "mssql+pyodbc://LENOVO-LOQ\\MSSQL/python?driver=ODBC+Driver+17+for+SQL+Server&Trusted_Connection=yes"
)
db = SQLAlchemy(app)