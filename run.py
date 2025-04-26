import os

from dotenv import load_dotenv

from app import create_app

# Load environment variables from .env file
load_dotenv()

app = create_app()

if __name__ == "__main__":
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    app.run(
        debug=app.config['DEBUG'],
        host=app.config["FLASK_RUN_HOST"],
        port=app.config["FLASK_RUN_PORT"]
    )
