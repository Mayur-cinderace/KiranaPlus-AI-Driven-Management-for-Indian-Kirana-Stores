# KiranaPlus – AI-Driven Management System for Indian Kirana Stores

<div align="center">

![KiranaPlus](https://img.shields.io/badge/Status-Active-brightgreen)
![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Flask](https://img.shields.io/badge/Flask-2.3.3-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

**Modernizing Indian Kirana Stores with AI-Powered Solutions**

[Features](#-features) • [Tech Stack](#-tech-stack) • [Installation](#-installation) • [API Docs](#-api-endpoints) • [Contributing](#-contributing)

</div>

---

## 📋 Overview

KiranaPlus is a comprehensive, AI-powered web application designed to digitize and modernize traditional Indian kirana (independent grocery) stores. By integrating intelligent billing, real-time inventory management, AI-driven insights, and OCR-based invoice processing, KiranaPlus enables store owners to optimize operations, reduce manual errors, and make data-driven business decisions.

**Key Benefits:**
- ✅ Reduce billing time and manual errors
- ✅ Real-time inventory tracking  
- ✅ AI-powered sales & inventory analytics
- ✅ Automated invoice processing via OCR
- ✅ Data-driven business insights

---

## ✨ Features

### 🧾 Smart Billing System
- **Dynamic Product Billing**: Quick and intuitive billing interface
- **Automatic Calculations**: Real-time total and tax calculations
- **Bill Generation**: Generate and print receipts instantly
- **Multiple Payment Options**: Support for various payment methods

### 📦 Inventory Management
- **Product Management**: Add, update, delete products with ease
- **Real-Time Tracking**: Track stock levels and quantities
- **Low-Stock Alerts**: Automatic notifications for low inventory
- **Price Management**: Dynamic pricing and bulk pricing support
- **Stock History**: Complete audit trail of inventory changes

### 🤖 AI-Powered Invoice Processing
- **OCR Technology**: Extract text from invoice images using PaddleOCR
- **Automated Data Entry**: Auto-populate inventory from supplier receipts
- **Multiple Formats**: Support for PNG, JPG, JPEG, BMP, TIFF
- **Error Reduction**: Minimize manual entry mistakes

### 📊 Advanced Analytics & Insights
- **Sales Analytics**: Track sales trends and patterns
- **Inventory Analysis**: Understand inventory turnover rates
- **Predictive Insights**: AI-driven forecasting using Prophet
- **Custom Reports**: Generate data-driven business reports
- **Performance Metrics**: KPIs and performance dashboards

### 🔐 Authentication & Security
- **User Registration**: Secure signup for retailers and users
- **Role-Based Access**: Different roles for store owners and staff
- **Data Security**: Secure database with MongoDB
- **CORS Protection**: Cross-origin request handling

### 🔍 Intelligent Search
- **Fast Product Lookup**: Quick product search functionality
- **Smart Filtering**: Filter by category, price range, stock status
- **Autocomplete**: Suggest products as you type
- **User-Friendly Interface**: Intuitive search experience

---

## 🛠️ Tech Stack

### **Backend**
- **Framework**: Flask 2.3.3 (Python Web Framework)
- **Database**: MongoDB (NoSQL Document Database)
- **OCR**: PaddleOCR (Optical Character Recognition)
- **AI/ML**: Google Generative AI (Gemini API)
- **Forecasting**: Facebook Prophet (Time Series Analysis)
- **Computer Vision**: OpenCV 4.8.1
- **Scientific Computing**: NumPy, Pandas
- **API**: Flask-CORS for cross-origin support

### **Frontend**
- **HTML5**: Semantic markup
- **CSS3**: Tailwind CSS for styling
- **JavaScript**: Vanilla JS for interactivity
- **Responsive Design**: Mobile-first approach

### **Dependencies**
```
flask==2.3.3
flask-cors==4.0.0
werkzeug==2.3.7
pymongo==4.5.0
opencv-python==4.8.1.78
numpy==1.24.3
google-generativeai==0.3.0
python-dotenv
python-dateutil
paddleocr
paddlepaddle
mlxtend
prophet
```

---

## 📁 Project Structure

```
KiranaPlus-AI-Driven-Management-for-Indian-Kirana-Stores/
│
├── 📄 Frontend Files
│   ├── index.html                 # Home page & dashboard
│   ├── billing.html               # Billing interface
│   ├── inventory.html             # Inventory management
│   ├── view_inventory.html        # View inventory details
│   ├── insights.html              # Analytics & insights
│   ├── ocr.html                   # Invoice OCR upload
│   ├── try_your_luck.html         # Interactive gamification feature
│   └── README.md                  # Project documentation
│
└── 🐍 Backend (Flask Application)
    └── backend/
        ├── app.py                 # Flask app initialization & routes
        ├── config.py              # Configuration management
        ├── database.py            # MongoDB connection & utilities
        ├── ocr_service.py         # OCR processing logic
        ├── utils.py               # Helper functions & validators
        ├── requirements.txt       # Python dependencies
        │
        └── routes/                # API Route Blueprints
            ├── __init__.py
            ├── auth_routes.py     # Authentication endpoints
            ├── bill_routes.py     # Billing endpoints
            ├── health_routes.py   # Health check endpoints
            ├── insights_routes.py # Analytics endpoints
            ├── inventory_routes.py# Inventory endpoints
            ├── ocr_routes.py      # OCR processing endpoints
            └── search_routes.py   # Search endpoints

```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.8+**
- **MongoDB** (local or cloud - MongoDB Atlas)
- **Git**
- **Node.js/npm** (optional, for frontend tools)

### Installation

#### 1. Clone the Repository
```bash
git clone https://github.com/Mayur-cinderace/KiranaPlus-AI-Driven-Management-for-Indian-Kirana-Stores.git
cd KiranaPlus-AI-Driven-Management-for-Indian-Kirana-Stores
```

#### 2. Backend Setup

##### Create Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

##### Install Dependencies
```bash
cd backend
pip install -r requirements.txt
```

##### Configure Environment Variables
Create a `.env` file in the `backend/` directory:
```env
# MongoDB Configuration (Required)
MONGO_URI=mongodb+srv://<username>:<password>@<cluster>.mongodb.net/<database>?retryWrites=true&w=majority

# Gemini API Configuration (Required)
GEMINI_API_KEY=your_gemini_api_key_here

# Server Configuration (Optional)
PORT=49285
DEBUG=True
SECRET_KEY=your_secret_key_here

# OCR Configuration (Optional)
MAX_FILE_SIZE=5242880  # 5MB in bytes
```

#### 3. Start MongoDB
```bash
# If using local MongoDB
mongod

# OR use MongoDB Atlas cloud service
```

#### 4. Run the Backend Server
```bash
cd backend
python app.py
```

The backend will start on `http://localhost:49285` and initialize PaddleOCR.

#### 5. Serve Frontend
```bash
# Using Python's built-in HTTP server
cd ..
python -m http.server 8000

# OR use any other HTTP server
# The frontend will be available at http://localhost:8000
```

---

## 🔗 API Endpoints

### Health Check
- **GET** `/health` - Server health status

### Authentication
- **POST** `/signup` - User registration
- **POST** `/login` - User login
- **POST** `/retailer-signup` - Retailer registration

### Inventory Management
- **GET** `/get-all-items` - Fetch all inventory items
- **POST** `/add-item` - Add new product
- **PUT** `/update-item/<item_id>` - Update product
- **DELETE** `/delete-item/<item_id>` - Delete product
- **GET** `/search-items` - Search products

### Billing
- **POST** `/generate-bill` - Generate bill for purchase
- **GET** `/bill-history` - Get billing history
- **GET** `/bill/<bill_id>` - Get specific bill

### OCR Processing
- **POST** `/upload-receipt` - Upload invoice image
- **POST** `/process-ocr` - Process OCR extraction
- **POST** `/save-receipt-items` - Save extracted items to inventory

### Analytics & Insights
- **GET** `/insights/sales` - Sales analytics
- **GET** `/insights/inventory` - Inventory analysis
- **GET** `/insights/trends` - Sales trends
- **GET** `/insights/predictions` - AI forecasting
- **GET** `/api/analytics/dashboard` - Dashboard metrics

---

## 🔐 Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MONGO_URI` | ✅ Yes | MongoDB connection string |
| `GEMINI_API_KEY` | ✅ Yes | Google Gemini API key |
| `PORT` | ❌ No | Server port (default: 49285) |
| `DEBUG` | ❌ No | Debug mode (default: True) |
| `SECRET_KEY` | ❌ No | Session/JWT secret |
| `MAX_FILE_SIZE` | ❌ No | Max upload size (default: 5MB) |

### Database Setup

#### MongoDB Collections
- **user_signups** - User account information
- **retailer_signups** - Retailer account information
- **kirana_inventory** - Product inventory data

#### Required Indexes
```javascript
// User collection
db.user_signups.createIndex({ "email": 1 }, { unique: true })

// Retailer collection
db.retailer_signups.createIndex({ "email": 1 }, { unique: true })

// Inventory collection
db.kirana_inventory.createIndex({ "kiranaId": 1 })
db.kirana_inventory.createIndex({ "productName": "text" })
```

---

## 💻 Usage

### For Store Owners

1. **Sign Up**: Register your kirana store
2. **Add Inventory**: Manually add products or use OCR for bulk import
3. **Manage Stock**: Track inventory levels and set low-stock alerts
4. **Generate Bills**: Quick billing interface for customers
5. **View Analytics**: Access sales trends and inventory insights
6. **Make Decisions**: Use AI insights to optimize stock and pricing

### For Developers

1. **Fork & Clone**: Get the repository
2. **Local Setup**: Follow installation steps
3. **API Testing**: Use Postman/Insomnia to test endpoints
4. **Custom Features**: Extend routes and add new functionality
5. **Database Migration**: Modify schema as needed

---

## 📊 Key Technologies Explained

### PaddleOCR
Optical Character Recognition for extracting text from invoice images. Supports multiple languages and is CPU-optimized.

### MongoDB
NoSQL database providing flexibility in document structure, easy scaling, and fast queries for inventory data.

### Google Generative AI (Gemini)
Advanced language model for generating insights, recommendations, and intelligent business analysis.

### Facebook Prophet
Time-series forecasting library for predicting future sales trends and inventory demands.

---

## 🐛 Troubleshooting

### Common Issues

**Issue**: MongoDB Connection Failed
```
Solution: Check MONGO_URI in .env file and ensure MongoDB service is running
```

**Issue**: GEMINI_API_KEY not found
```
Solution: Add GEMINI_API_KEY to .env file
Get free API key from: https://ai.google.dev/
```

**Issue**: CORS Errors
```
Solution: Check that frontend is running on http://localhost:8000
Verify CORS origins in app.py match your frontend URL
```

**Issue**: PaddleOCR Initialization Failed
```
Solution: Ensure all dependencies are installed correctly
pip install --upgrade paddleocr paddlepaddle
```

**Issue**: Port Already in Use
```
Solution: Change PORT in .env file or kill the process using the port
Windows: netstat -ano | findstr :49285 then taskkill /PID <PID>
Linux: lsof -i :49285 then kill -9 <PID>
```

---

## 🤝 Contributing

We welcome contributions! Please follow these steps:

1. **Fork** the repository
2. **Create** a feature branch: `git checkout -b feature/AmazingFeature`
3. **Commit** your changes: `git commit -m 'Add AmazingFeature'`
4. **Push** to the branch: `git push origin feature/AmazingFeature`
5. **Open** a Pull Request with detailed description

### Code Guidelines
- Follow PEP 8 for Python code
- Use meaningful variable and function names
- Add docstrings to functions
- Write comments for complex logic
- Test your changes thoroughly

---

## 📝 License

This project is licensed under the **MIT License** - see the LICENSE file for details.

---


## 🎯 Roadmap

- [ ] Mobile app (React Native)
- [ ] Multi-language support
- [ ] Advanced reporting dashboards
- [ ] Supplier management system
- [ ] Customer loyalty program
- [ ] Integration with payment gateways
- [ ] Cloud deployment automation
- [ ] API documentation with Swagger

---

## 🙏 Acknowledgments

- **Flask** - Microframework for web development
- **MongoDB** - NoSQL database
- **PaddleOCR** - OCR technology
- **Google Generative AI** - Advanced AI capabilities
- **Tailwind CSS** - Frontend styling
- **Open Source Community** - For incredible tools and libraries

---

<div align="center">

**⭐ If you find this project helpful, please star it on GitHub!**

</div>

```
