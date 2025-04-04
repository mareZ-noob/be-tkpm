# System Design Project

## Overview


## Features


## Installation
### Prerequisites
- Python 3.10.12
- Redis

### Setup
1. Clone the repository
    ```bash
    git clone https://github.com/mareZ-noob/be-tkpm.git
    cd be-tkpm
    ```
2. Create a virtual environment and activate it:
    ```bash
    python3 -m venv venv  # On Windows use `python` instead of `python3`
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```
3. Install the dependencies:
    ```bash
    pip install -r requirements.txt
    ```
4. Create .env file and add the following configurations, adjust them according to your local environment:
    ```bash
   FLASK_ENV=development
   FLASK_APP=run.py
   FLASK_RUN_HOST=localhost
   FLASK_RUN_PORT=5000
   SECRET_KEY=thissecretkeyisverysecret
   
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   POSTGRES_USER=admin
   POSTGRES_PASSWORD=admin
   POSTGRES_DB=tkpm
   
   REDIS_HOST=localhost
   REDIS_PORT=6379
   
   MAIL_SERVER=smtp.gmail.com
   MAIL_PORT=587
   MAIL_USERNAME=
   MAIL_PASSWORD=
   
   GEMINI_API_KEY=
   OPEN_ROUTER_API_KEY=
   ASSEMBLY_AI_API_KEY=
   TIKTOK_SESSION_ID=
   PEXELS_API_KEY=
   
   CLOUDINARY_CLOUD_NAME=
   CLOUDINARY_API_KEY=
   CLOUDINARY_API_SECRET=
   CLOUDINARY_URL=
   
   FRONTEND_URL=http://localhost:5173
    ```
## Usage
### First time setup to create the database
```bash
flask db upgrade
```
### Create a new migration
```bash
flask db migrate -m "migration message"
```
### Apply the changes to the database
```bash
flask db upgrade
```
### Run the application
```bash
./start.sh  # If you want to use Docker Compose
# Or 
celery -A celery_worker.celery worker --loglevel=info # Start the Celery worker
python3 run.py  # On Windows use `python` instead of `python3`
```
### Format the code
```bash
./format-code.sh
# Or 
isort .
flake8 .
```
