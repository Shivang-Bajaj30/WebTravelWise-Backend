from msconfig import *
from datetime import datetime
import json

class Trip(db.Model):
    __tablename__ = "trips"
    id = db.Column(db.Integer, primary_key=True)
    location = db.Column(db.String(200), nullable=False)
    travelers = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.String(50), nullable=False)
    end_date = db.Column(db.String(50), nullable=False)
    preferences = db.Column(db.Text, nullable=True)
    itinerary_data = db.Column(db.Text, nullable=True)  # Stores full AI-generated JSON
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        # Parse itinerary_data back to dict if it's a JSON string
        itinerary = None
        if self.itinerary_data:
            try:
                itinerary = json.loads(self.itinerary_data)
            except (json.JSONDecodeError, TypeError):
                itinerary = self.itinerary_data

        return {
            "id": self.id,
            "location": self.location,
            "travelers": self.travelers,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "preferences": self.preferences,
            "itinerary_data": itinerary,
            "created_at": self.created_at,
        }
