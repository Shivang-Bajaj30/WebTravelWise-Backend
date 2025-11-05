from msconfig import *
from models.User import *
from models.Trips import *

from werkzeug.security import generate_password_hash, check_password_hash
from AI_Gen import generate_itinerary

# app = Flask(__name__)

@app.route('/')
def home():
    return jsonify(message="Flask backend is running and connected to SQL Server! 🚀")

@app.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')

    if not name or not email or not password:
        return jsonify(error="All fields are required"), 400

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify(error="User already exists"), 400

    hashed_password = generate_password_hash(password)
    new_user = User(name=name, email=email, password=hashed_password)
    db.session.add(new_user)
    db.session.commit()

    return jsonify(message="Signup successful!"), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password, password):
        return jsonify(error="Invalid email or password"), 401

    access_token = create_access_token(identity={"id": user.id, "email": user.email, "name": user.name})
    return jsonify(
        message="Login successful ✅",
        user=user.to_dict(),
        token=access_token
    ), 200

# ------------------- AI ITINERARY ROUTE -------------------
@app.route("/generate_itinerary", methods=["POST"])
def generate_itinerary_route():
    try:
        data = request.get_json()
        destination = data.get("destination") or data.get("location")
        travelers = data.get("travelers")
        start_date = data.get("startDate")
        end_date = data.get("endDate")
        preferences = data.get("preferences", "")

        if not destination or not travelers or not start_date or not end_date:
            return jsonify(error="All required fields must be filled"), 400

        # --- Call AI Prompt File ---
        ai_response = generate_itinerary(
            destination=destination,
            travelers=travelers,
            start_date=start_date,
            end_date=end_date,
            preferences=preferences,
        )

        # --- Save to DB ---
        new_trip = Trip(
            location=destination,
            travelers=travelers,
            start_date=start_date,
            end_date=end_date,
            preferences=preferences,
        )
        db.session.add(new_trip)
        db.session.commit()

        return jsonify(message="Itinerary generated successfully!", data=ai_response), 200

    except Exception as e:
        print("Error:", str(e))
        return jsonify(error="Failed to generate itinerary", details=str(e)), 500

# ------------------- MAIN -------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
