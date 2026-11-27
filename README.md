# TourismPlanner ✈️

**TourismPlanner** is a Django-based web application designed to simplify travel planning and destination discovery through a unified platform. It enables users to explore tourist destinations, discover nearby attractions, save interesting places, organize day-wise travel itineraries, optimize routes, manage trip budgets and expenses, and access weather information.

The application integrates geographic, routing, and weather services to provide location-based information and assist users in organizing their journeys. It also provides a dedicated administrative interface for managing registered users.

---

## Table of Contents

- [Project Overview](#-project-overview)
- [Key Features](#-key-features)
- [System Architecture](#-system-architecture)
- [Technology Stack](#-technology-stack)
- [External Service Integrations](#-external-service-integrations)
- [Project Structure](#-project-structure)
- [Application Workflow](#-application-workflow)
- [Security Features](#-security-features)
- [Performance and Reliability](#-performance-and-reliability)
- [Installation and Setup](#-installation-and-setup)
- [Environment Configuration](#-environment-configuration)
- [Running the Application](#-running-the-application)
- [User Roles](#-user-roles)
- [Future Enhancements](#-future-enhancements)
- [Limitations and Dependencies](#-limitations-and-dependencies)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🌍 Project Overview

Planning a trip involves several activities, including discovering destinations, identifying nearby attractions, arranging travel schedules, estimating expenses, and checking weather conditions.

TourismPlanner brings these activities together in a single web application.

The application provides two primary user roles:

**1. Registered User**

Registered users can explore destinations, save places, create trips, manage itineraries, optimize travel routes, track expenses, retrieve weather information, and download trip details as PDF documents.

**2. Administrator**

Administrators can access a dedicated administrative interface to view registered users, inspect individual user details, manage account status, and delete user accounts.

The application follows a modular architecture, with separate modules for authentication, destination discovery, trip management, and administration.

---

## ✨ Key Features

### 1. User Registration and Authentication

TourismPlanner implements an email-based OTP verification mechanism to provide an additional authentication layer.

Features include:

- User registration with required personal information.
- Registration form validation.
- Duplicate email and mobile number detection.
- Email-based OTP verification during registration.
- Six-digit OTP generation.
- OTP expiration and attempt-limit enforcement.
- OTP resend functionality with cooldown restrictions.
- Login using registered email address and password.
- Additional OTP verification during login.
- Session-based authentication.
- Protected routes for authenticated users.
- Secure logout functionality.

**Registration workflow:**

1. User submits the registration form.
2. The application validates the submitted information.
3. Duplicate account details are checked.
4. A pending user account is created.
5. A six-digit OTP is generated and sent through Gmail SMTP.
6. The user submits the received OTP.
7. The application validates the OTP and completes account verification.

**OTP security policy:**

| Parameter | Registration OTP |
|---|---|
| OTP length | 6 digits |
| Expiration | 5 minutes |
| Maximum attempts | 5 |
| Resend cooldown | 60 seconds |
| Delivery mechanism | Gmail SMTP |

Login OTP verification follows the configured login challenge and attempt-control mechanism.

### 2. Destination Exploration

The Explore module allows users to discover tourist destinations and places of interest.

Features include:

- Destination search.
- Location-based exploration.
- City and regional place discovery.
- Category-based filtering.
- Place-type and subcategory filtering.
- Live geographic search.
- Retrieval of stored destination information.
- Pagination of search results.
- Destination image lookup.
- Explore-related weather information.

The application uses MongoDB for stored place information and integrates with OpenStreetMap-related services for geographic search and destination discovery.

### 3. Interactive Map and Nearby Attractions

The application provides map-based destination exploration using Leaflet and geographic information from OpenStreetMap services.

Features include:

- Interactive map visualization.
- Location-based nearby attraction discovery.
- Retrieval of nearby points of interest.
- Category-based filtering.
- Distance calculation from the supplied geographic coordinates.
- Display of available place names, categories, addresses, and coordinates.
- Duplicate-place filtering.
- Directions and navigation links.

Nearby attraction discovery uses geographic coordinates to retrieve and process relevant location information.

### 4. Saved Places Management

Users can maintain a personal collection of interesting destinations.

Features include:

- Save destinations for future visits.
- View previously saved places.
- Remove saved destinations.
- Associate saved places with the authenticated user.
- Prevent duplicate saved-place entries.
- Restrict access to user-specific saved-place information.

### 5. Trip Creation and Management

The Trips module enables users to create and manage their travel plans.

Features include:

- Create new trips.
- Provide trip title and travel dates.
- Set an initial trip budget.
- View all personal trips.
- Access individual trip details.
- Update trip information.
- Delete existing trips.
- Associate trips with their respective owners.

Each trip maintains its own travel information and itinerary.

### 6. Day-Wise Itinerary Management

Users can organize destinations into individual days of a trip.

Features include:

- Add destinations to a selected trip day.
- Remove destinations from an itinerary.
- Reorder destinations within a day.
- Mark destinations as visited.
- Update day-completion status.
- Maintain destination order.
- Validate itinerary operations.
- Ensure that only the trip owner can modify the itinerary.

This functionality allows users to organize their journeys into structured daily schedules.

### 7. Day-Wise Route Optimization

TourismPlanner provides a route optimization feature to suggest a more efficient visiting order for destinations within a selected itinerary day.

The system integrates with the **OSRM Table API** to obtain road-distance information between destinations.

The optimization process uses two algorithms:

**Nearest Neighbour Algorithm**

- Starts from the configured starting location.
- Identifies the nearest unvisited destination.
- Adds that destination to the route.
- Repeats the process until all destinations are visited.
- Generates an initial route order.

**2-opt Optimization Algorithm**

- Takes the initial route generated by Nearest Neighbour.
- Examines possible route improvements by reversing sections of the route.
- Compares the resulting road distances.
- Applies improvements when a shorter route is obtained.
- Produces a suggested optimized destination order.

**Route optimization functionality:**

- Retrieve road-distance information through OSRM.
- Maintain a fixed starting location.
- Calculate original route distance.
- Calculate optimized route distance.
- Display the suggested destination order.
- Compare original and optimized routes.
- Allow users to accept the suggested route.
- Update the itinerary after route acceptance.

**Note:** Route optimization uses heuristic algorithms. Therefore, the suggested route is not guaranteed to be the globally optimal route.

### 8. Trip Budget and Expense Management

Users can manage their estimated travel budget and record expenses associated with individual trips.

Features include:

- Set or update trip budgets.
- Add new expenses.
- Specify expense amount.
- Select expense categories.
- Add expense descriptions.
- Record expense dates.
- Associate expenses with itinerary days where applicable.
- Update existing expenses.
- Delete expenses.
- Retrieve trip expense summaries.

This module helps users monitor their travel spending and organize financial information.

### 9. Weather Information

TourismPlanner integrates with the **Open-Meteo API** to retrieve weather information for selected geographic locations.

Two weather-related functionalities are available.

**Explore Weather**

- Retrieve current weather information for a selected destination.
- Accept latitude and longitude coordinates.
- Validate geographic coordinates.
- Display available temperature information.
- Display maximum and minimum temperatures.
- Retrieve rain-probability information.
- Use caching to reduce repeated requests.

**Trip Weather**

- Retrieve weather information associated with a trip.
- Accept destination coordinates.
- Consider the requested travel date range.
- Retrieve available daily forecast information.
- Display weather information relevant to trip planning.

### 10. Nearby Places for Trip Planning

In addition to Explore-related nearby attractions, TourismPlanner provides a separate nearby-place discovery functionality within trip planning.

Features include:

- Discover places around a trip location.
- Retrieve nearby geographic information.
- Filter places using available categories.
- Display available place information.
- Support pagination.
- Provide directions links.

This functionality is designed to help users discover additional places while organizing their trips.

### 11. Trip PDF Download

TourismPlanner provides a facility to download individual trip information as a PDF document.

The application uses **ReportLab** for PDF generation.

Workflow:

1. The authenticated user selects a trip.
2. The application receives the requested trip identifier.
3. Trip ownership is verified.
4. Required trip information is retrieved.
5. The PDF document is generated.
6. The generated PDF is returned to the browser.
7. The user can download the trip document.

The PDF download operation is restricted to the authenticated owner of the requested trip.

### 12. Administrative Dashboard and User Management

TourismPlanner provides a separate administrative interface for authorized administrators.

Features include:

- Separate administrator login.
- Administrator session management.
- Administrative dashboard.
- Registered user listing.
- Individual user details.
- User account status management.
- Activate or deactivate user accounts.
- Delete user accounts.
- Administrator logout.

Administrative operations are restricted to authorized administrators.

---

## 🏗️ System Architecture

TourismPlanner follows a modular, browser-based client-server architecture.

The application consists of four major layers:

**1. Presentation Layer**

- HTML5
- CSS3
- JavaScript
- Leaflet

Responsible for rendering pages, accepting user input, displaying information, and handling frontend interactions.

**2. Application Layer**

- Python
- Django

Responsible for request handling, URL routing, application logic, authentication, session management, trip operations, and administrative functionality.

**3. Data Layer**

- MongoDB
- PyMongo
- SQLite

MongoDB stores application information, including user accounts, OTP challenges, places, saved places, trips, itineraries, and expenses.

SQLite is configured for Django-related database operations, including session management.

**4. External Services Layer**

- Nominatim
- Overpass API
- OSRM
- Open-Meteo
- Gmail SMTP

These services provide geographic information, destination discovery, road-distance calculations, weather information, and email-based OTP delivery.

### High-Level Architecture

```text
              USER / ADMINISTRATOR
                       |
                       v
                Web Browser
                       |
             HTML / CSS / JavaScript
                       |
                       v
                Django Backend
                       |
          +------------+------------+
          |            |            |
          v            v            v
       Accounts      Places       Trips
          |            |            |
          +------------+------------+
                       |
                       v
                 Database Layer
                       |
                +------+------+
                |             |
                v             v
             MongoDB        SQLite
                |
                v
          External Services
                |
      +---------+---------+
      |         |         |
      v         v         v
  OpenStreetMap  OSRM  Open-Meteo
      |
      v
   Nominatim / Overpass

      Gmail SMTP
          |
          v
      OTP Emails
```

---

## 🛠️ Technology Stack

| Technology | Purpose |
|---|---|
| Python | Backend programming language |
| Django 5.0.1 | Web application framework |
| MongoDB | Primary application data storage |
| PyMongo | MongoDB connectivity |
| SQLite | Django-related database operations and sessions |
| HTML5 | Webpage structure |
| CSS3 | Styling and layout |
| JavaScript | Frontend interactions and API communication |
| Leaflet | Interactive map visualization |
| OpenStreetMap | Geographic and destination data |
| Nominatim | Geocoding and geographic search |
| Overpass API | Retrieval of geographic objects and points of interest |
| OSRM | Road-distance information and route optimization |
| Open-Meteo | Weather information and forecasts |
| Gmail SMTP | Email-based OTP delivery |
| ReportLab | PDF generation |
| python-dotenv | Environment variable management |
| Requests | HTTP communication with external services |

---

## 🌐 External Service Integrations

TourismPlanner uses external services to provide geographic, routing, and weather-related functionality.

| Service | Purpose |
|---|---|
| Nominatim | Geographic search and geocoding |
| Overpass API | Retrieval of OpenStreetMap attractions and geographic objects |
| OSRM Table API | Road-distance matrix retrieval for route optimization |
| Open-Meteo | Current and forecast weather information |
| Gmail SMTP | Sending registration and login OTP emails |
| OpenStreetMap | Geographic map data used with Leaflet |

### External Service Communication

The Django backend communicates with external services through HTTP/HTTPS requests.

The application processes the returned information and provides relevant results to the frontend.

External service availability, response time, data quality, and request limitations may affect the corresponding application features.

---

## 📁 Project Structure

The project is organized into separate Django applications and shared resources.

```text
TourismPlanner/
│
├── apps/
│   │
│   ├── accounts/
│   │   ├── Registration and Login
│   │   ├── OTP Verification
│   │   ├── Session Management
│   │   └── User Dashboard
│   │
│   ├── adminpanel/
│   │   ├── Administrator Authentication
│   │   ├── Admin Dashboard
│   │   └── User Management
│   │
│   ├── places/
│   │   ├── Destination Exploration
│   │   ├── Geographic Search
│   │   ├── Nearby Attractions
│   │   ├── Saved Places
│   │   └── Weather and Place Services
│   │
│   └── trips/
│       ├── Trip Management
│       ├── Itinerary Management
│       ├── Route Optimization
│       ├── Budget and Expenses
│       ├── Trip Weather
│       ├── Nearby Places
│       └── PDF Generation
│
├── config/
│   ├── settings.py
│   ├── urls.py
│   └── Django Configuration
│
├── core/
│   └── Shared Database Utilities
│
├── static/
│   ├── CSS/
│   ├── JavaScript/
│   └── Other Static Resources
│
├── templates/
│   └── HTML Templates
│
├── .env.example
├── .gitignore
└── manage.py
```

---

## 🔄 Application Workflow

### Registered User Workflow

```text
        Registration
             |
             v
      Registration OTP
         Verification
             |
             v
       User Login
             |
             v
         Login OTP
         Verification
             |
             v
       User Dashboard
             |
      +------+------+
      |      |      |
      v      v      v
    Explore Saved  Trips
    Places  Places   |
                    v
               Create Trip
                    |
                    v
              Add Destinations
                    |
                    v
             Create Itinerary
                    |
                    v
             Optimize Routes
                    |
                    v
             Manage Expenses
                    |
                    v
              Check Weather
                    |
                    v
               Download PDF
```

### Administrator Workflow

```text
       Administrator Login
                |
                v
        Authentication
                |
                v
       Admin Dashboard
                |
                v
          User Listing
                |
                v
         User Details
                |
          +-----+-----+
          |           |
          v           v
     Change Status  Delete User
          |           |
          +-----+-----+
                |
                v
           Admin Logout
```

---

## 🔐 Security Features

TourismPlanner incorporates security measures to protect user accounts and application data.

- Passwords are stored as hashes using Django's password-hashing functionality.
- Registration and login use email-based OTP verification.
- OTP expiration and attempt limits are enforced.
- OTP resend cooldown restrictions are implemented.
- Session-based authentication protects user-specific functionality.
- Invalid authenticated sessions are handled by the application.
- Inactive or ineligible accounts are restricted from normal user access.
- Duplicate email addresses and mobile numbers are prevented.
- Users can access only their own trips and saved places.
- Trip ownership is validated before modification and PDF generation.
- Administrative operations require authorized administrator access.
- Password hashes are excluded from ordinary user information and administrative user views.
- User deletion also removes associated trips and saved places.

Sensitive configuration values are maintained through environment variables rather than being committed to the source repository.

---

## ⚡ Performance and Reliability

The application incorporates caching and external-service error handling to improve its operation.

### Caching

| Functionality | Cache Duration |
|---|---|
| Successfully retrieved destination images | 24 hours |
| Explore weather information | 60 minutes |

Caching helps reduce repeated external API requests and unnecessary data retrieval.

### External Service Handling

- External service requests use configured timeout values.
- Invalid geographic coordinates are validated.
- Unavailable external services are handled through relevant error-handling mechanisms.
- Missing or unavailable external information may result in an error response or empty results.
- Database and external-service dependencies are handled by their respective application modules.

### Software Quality Attributes

- **Usability:** Simple browser-based user interface.
- **Maintainability:** Separate application modules for different functionalities.
- **Modularity:** Independent Accounts, Places, Trips, and Admin modules.

---

## 🚀 Installation and Setup

Follow these instructions to run TourismPlanner locally.

### Prerequisites

Ensure that the following software is installed:

- Python 3
- MongoDB
- Git
- A modern web browser
- Internet connectivity

### 1. Clone the Repository

```bash
git clone https://github.com/DI133/TourismPlanner.git
```

Navigate to the project directory:

```bash
cd TourismPlanner
```

### 2. Create a Virtual Environment

```bash
python -m venv venv
```

Activate the environment.

**Windows PowerShell:**

```powershell
.\venv\Scripts\Activate.ps1
```

**Linux/macOS:**

```bash
source venv/bin/activate
```

### 3. Install Dependencies

If the repository contains a `requirements.txt` file:

```bash
pip install -r requirements.txt
```

Otherwise, install the required packages listed in the project dependency configuration.

### 4. Configure Environment Variables

Create a `.env` file in the project root directory.

Use `.env.example` as the configuration reference.

Example configuration:

```env
DJANGO_SECRET_KEY=your_django_secret_key
DEBUG=True

MONGODB_URI=mongodb://localhost:27017/
MONGODB_DB=tourismplanner

EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_email_app_password
DEFAULT_FROM_EMAIL=your_email@gmail.com
```

Replace the example values with your own configuration.

**Important:** Never commit your actual `.env` file, secret keys, database credentials, or email passwords to GitHub.

### 5. Start MongoDB

Ensure that the MongoDB server is running and that the configured database is accessible.

The application uses MongoDB through PyMongo for application-related data storage.

### 6. Apply Django Migrations

Run:

```bash
python manage.py check
```

Then:

```bash
python manage.py migrate
```

This applies the required Django database migrations, including framework-related database operations.

### 7. Start the Development Server

```bash
python manage.py runserver
```

Open the application in your browser:

```text
http://127.0.0.1:8000/
```

TourismPlanner should now be accessible locally.

---

## 👥 User Roles

| Functionality | Registered User | Administrator |
|---|:---:|:---:|
| User registration | ✓ | — |
| User login | ✓ | — |
| OTP verification | ✓ | — |
| User dashboard | ✓ | — |
| Explore destinations | ✓ | — |
| Discover nearby attractions | ✓ | — |
| Manage saved places | ✓ | — |
| Create and manage trips | ✓ | — |
| Manage itineraries | ✓ | — |
| Optimize routes | ✓ | — |
| Manage trip budgets | ✓ | — |
| Manage expenses | ✓ | — |
| Access weather information | ✓ | — |
| Download trip PDF | ✓ | — |
| Administrator login | — | ✓ |
| View registered users | — | ✓ |
| View user details | — | ✓ |
| Change account status | — | ✓ |
| Delete user accounts | — | ✓ |

---

## 🔮 Future Enhancements

The following items are identified as potential future enhancements in the project's SRS. They are not presented as currently implemented features.

- **Multilingual Support:** Provide the application interface in multiple languages.
- **Dedicated Mobile Application:** Develop Android and iOS applications.
- **AI-Based Recommendations:** Introduce personalized destination and itinerary recommendations.
- **Social Features:** Allow users to share trips and itineraries with others.
- **Restaurant Crowd and Waiting-Time Estimation:** Provide estimated crowd levels, waiting times, and expected table availability for nearby restaurants.

---

## ⚠️ Limitations and Dependencies

- An active internet connection is required for application access and external service communication.
- Geographic search depends on Nominatim and Overpass API availability.
- Route optimization depends on road-distance information returned by OSRM.
- Weather information depends on Open-Meteo availability and supported forecast data.
- OTP delivery depends on the configured Gmail SMTP service.
- External providers may impose usage restrictions and request limits.
- Route optimization provides a heuristic suggestion and does not guarantee a globally optimal route.
- The completeness of destination and weather information depends on external data availability.

---

## 🤝 Contributing

Contributions and suggestions for improving TourismPlanner are welcome.

1. Fork the repository.
2. Create a new feature branch.
3. Implement your changes.
4. Test the modified functionality.
5. Commit your changes with meaningful commit messages.
6. Submit a pull request describing the changes.

---



**TourismPlanner – Discover destinations, organize journeys, and plan smarter trips.** ✈️
