from flask import Blueprint, request, jsonify
from datetime import datetime
from database import get_user_collection, get_retailer_collection, is_db_connected
from utils import generate_unique_kirana_id, validate_mobile_number, validate_kirana_id
import logging

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/signup", methods=["POST"])
def signup():
    """Create user account"""
    try:
        if not is_db_connected():
            return jsonify({"error": "Database connection not available"}), 500
            
        data = request.json
        print("Received signup data:", data)
        
        # Validate required fields
        full_name = data.get("fullName", "").strip()
        mobile = data.get("mobile", "").strip()
        dob = data.get("dob", "").strip()
        role = data.get("role", "").strip()
        
        # Validation
        if not full_name:
            return jsonify({"error": "Full name is required"}), 400
        
        # Validate mobile number
        is_valid, message = validate_mobile_number(mobile)
        if not is_valid:
            return jsonify({"error": message}), 400
        
        if not role or role not in ['user', 'retailer']:
            return jsonify({"error": "Please select a valid role (user or retailer)"}), 400
        
        # Get appropriate collection based on role
        if role == "retailer":
            collection = get_retailer_collection()
        else:
            collection = get_user_collection()
        
        # Check if mobile number already exists
        if collection.count_documents({"mobile": mobile}) > 0:
            return jsonify({"error": "Mobile number already registered"}), 400
        
        # Generate unique Kirana ID
        kirana_id = generate_unique_kirana_id(collection)
        
        # Prepare document for insertion
        # Prepare document for insertion
        user_doc = {
            "fullName": full_name,
            "mobile": mobile,
            "role": role,
            "kiranaId": kirana_id,
            "createdAt": datetime.utcnow(),
            "isVerified": False,
            "loyalty_points": 0
        }
        
        # Add DOB if provided
        if dob:
            try:
                dob_date = datetime.strptime(dob, "%Y-%m-%d")
                user_doc["dateOfBirth"] = dob_date
            except ValueError:
                return jsonify({"error": "Invalid date format for date of birth"}), 400
        
        print("Inserting user document:", user_doc)
        
        # Insert into database
        result = collection.insert_one(user_doc)
        
        if result.inserted_id:
            print(f"User created with ID: {result.inserted_id}")
            return jsonify({
                "message": "Account created successfully",
                "id": str(result.inserted_id),
                "kiranaId": kirana_id,
                "role": role
            }), 201
        else:
            return jsonify({"error": "Failed to create account"}), 500
            
    except Exception as e:
        print(f"Signup error: {e}")
        logging.error(f"Signup error: {e}")
        return jsonify({"error": "Internal server error occurred"}), 500

@auth_bp.route("/login", methods=["POST"])
def login():
    """Login endpoint - Verify user with mobile, kiranaId and role"""
    try:
        if not is_db_connected():
            return jsonify({"error": "Database connection not available"}), 500
            
        data = request.json
        print("Received login data:", data)
        
        mobile = data.get("mobile", "").strip()
        kirana_id = data.get("kiranaId")
        role = data.get("role", "").strip()
        
        # Validate mobile number
        is_valid, message = validate_mobile_number(mobile)
        if not is_valid:
            return jsonify({"error": message}), 400
        
        # Validate Kirana ID
        is_valid, validated_id = validate_kirana_id(kirana_id)
        if not is_valid:
            return jsonify({"error": validated_id}), 400
        kirana_id = validated_id
            
        if not role or role not in ['user', 'retailer']:
            return jsonify({"error": "Please select a valid role (user or retailer)"}), 400
        
        # Get appropriate collection based on role
        if role == "retailer":
            collection = get_retailer_collection()
        else:
            collection = get_user_collection()
        
        print(f"Searching for user: mobile={mobile}, kiranaId={kirana_id}, role={role}")
        
        # Find user with all three matching criteria
        user = collection.find_one({
            "mobile": mobile,
            "kiranaId": kirana_id,
            "role": role
        })
        
        if not user:
            # Check what doesn't match for better error messages
            mobile_exists = collection.find_one({"mobile": mobile})
            kirana_exists = collection.find_one({"kiranaId": kirana_id})
            role_match = collection.find_one({"mobile": mobile, "role": role})
            
            if not mobile_exists:
                return jsonify({"error": "Mobile number not registered"}), 404
            elif not kirana_exists:
                return jsonify({"error": "Invalid Kirana ID"}), 404
            elif not role_match:
                return jsonify({"error": f"This mobile number is not registered as a {role}"}), 404
            else:
                return jsonify({"error": "Invalid login credentials. Please check your mobile number, Kirana ID, and role"}), 404
        
        print(f"User found: {user['fullName']} (ID: {user['_id']})")
        
        # Update last login timestamp
        collection.update_one(
            {"_id": user["_id"]}, 
            {"$set": {"lastLoginAt": datetime.utcnow()}}
        )
        
        # Prepare response data
        response_data = {
            "message": "Login successful",
            "kiranaId": user.get("kiranaId"),
            "fullName": user.get("fullName"),
            "role": user.get("role"),
            "mobile": user.get("mobile"),
            "userId": str(user.get("_id"))
        }
        
        # Add redirect URL if role is retailer
        if role == "retailer":
            response_data["redirectUrl"] = "http://127.0.0.1:8000/inventory.html"
        
        return jsonify(response_data), 200
        
    except Exception as e:
        print(f"Login error: {e}")
        logging.error(f"Login error: {e}")
        return jsonify({"error": "Internal server error occurred"}), 500

@auth_bp.route("/verify-kirana-id", methods=["POST"])
def verify_kirana_id():
    """Verify if a Kirana ID exists and return basic info"""
    try:
        if not is_db_connected():
            return jsonify({"error": "Database connection not available"}), 500
            
        data = request.json
        kirana_id = data.get("kiranaId")
        
        # Validate Kirana ID
        is_valid, validated_id = validate_kirana_id(kirana_id)
        if not is_valid:
            return jsonify({"error": validated_id}), 400
        kirana_id = validated_id
        
        # Search in both databases
        user_found = None
        user_role = None
        
        # Check user_signups
        user_collection = get_user_collection()
        user = user_collection.find_one({"kiranaId": kirana_id})
        if user:
            user_found = user
            user_role = "user"
        
        # Check retailer_signups if not found in users
        if not user_found:
            retailer_collection = get_retailer_collection()
            user = retailer_collection.find_one({"kiranaId": kirana_id})
            if user:
                user_found = user
                user_role = "retailer"
        
        if not user_found:
            return jsonify({"error": "Kirana ID not found"}), 404
        
        # Return basic info (don't expose sensitive data)
        return jsonify({
            "message": "Kirana ID verified",
            "kiranaId": kirana_id,
            "fullName": user_found.get("fullName"),
            "role": user_role,
            "mobile": user_found.get("mobile")[-4:].rjust(10, '*')  # Mask mobile number
        }), 200
        
    except Exception as e:
        print(f"Verify Kirana ID error: {e}")
        logging.error(f"Verify Kirana ID error: {e}")
        return jsonify({"error": "Internal server error occurred"}), 500