# TourismPlanner ✈️

**TourismPlanner** is a Django-based web application designed to simplify travel planning and destination discovery. It helps users explore tourist destinations, discover nearby places, save interesting locations, and organize their trips through an interactive interface.

## ✨ Features

### 1. User Authentication
- User registration and login
- Email OTP verification
- OTP-based login verification
- Session-based authentication

### 2. Destination Discovery
- Explore tourist destinations
- Search and filter places by location and category
- Discover nearby attractions and points of interest
- Interactive map-based exploration
- Save and manage favorite places

### 3. Trip Planning
- Create and manage travel plans
- Organize trip itineraries
- Discover nearby places for planned trips
- Access weather information for travel planning
- Route and trip optimization functionality

### 4. Admin Panel
- Dedicated administrative interface
- User management
- User details and dashboard

## 🛠️ Tech Stack

| Technology | Purpose |
|---|---|
| Python | Backend programming |
| Django | Web application framework |
| MongoDB | Application data storage |
| SQLite | Django session and framework database |
| HTML5 | Page structure |
| CSS3 | Styling |
| JavaScript | Frontend interactions |
| Leaflet | Interactive maps |
| OpenStreetMap services | Geographic and destination data |
| ReportLab | PDF generation |

## 📁 Project Structure

```text
TourismPlanner/
│
├── apps/
│   ├── accounts/       # Authentication and user management
│   ├── adminpanel/     # Administrative functionality
│   ├── places/         # Destination discovery and saved places
│   └── trips/          # Trip planning and itinerary features
│
├── config/             # Django settings and URL configuration
├── core/               # Shared database utilities
├── static/             # CSS and JavaScript files
├── templates/          # HTML templates
├── .env.example        # Environment variable template
├── .gitignore
└── manage.py
```

## 🚀 Getting Started

### Prerequisites

- Python 3
- MongoDB
- Git

### 1. Clone the repository

```bash
git clone https://github.com/DI133/TourismPlanner.git
cd TourismPlanner
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

Activate it:

**Windows PowerShell**
```powershell
.\venv\Scripts\Activate.ps1
```

**Linux/macOS**
```bash
source venv/bin/activate
```

### 3. Install dependencies

Install the project's required Python packages. See the dependency list provided with the project.

### 4. Configure environment variables

Create a `.env` file in the project root using `.env.example` as a reference.

Configure your own values for:

- `MONGODB_URI`
- `MONGODB_DB`
- `DJANGO_SECRET_KEY`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `DEFAULT_FROM_EMAIL`

Never commit your actual `.env` file or credentials to GitHub.

### 5. Start MongoDB

Make sure your MongoDB server is running and the configured database is accessible.

### 6. Run the application

```bash
python manage.py check
python manage.py migrate
python manage.py runserver
```

Open your browser:

```text
http://127.0.0.1:8000/
```

## 🔐 Security

- Sensitive configuration is managed through environment variables.
- `.env` files are excluded from version control.
- Authentication and OTP workflows are implemented in the accounts module.
