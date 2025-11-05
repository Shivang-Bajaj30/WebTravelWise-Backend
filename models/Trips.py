from msconfig import *
from datetime import datetime

class Trip(db.Model):
    __tablename__ = "trips"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    location = db.Column(db.String(200), nullable=False)
    travelers = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.String(50), nullable=False)
    end_date = db.Column(db.String(50), nullable=False)
    preferences = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "location": self.location,
            "travelers": self.travelers,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "preferences": self.preferences,
            "created_at": self.created_at,
        }
