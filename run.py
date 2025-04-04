from dotenv import load_dotenv

from app import create_app

load_dotenv()

app = create_app()

if __name__ == "__main__":
    app.run(
        debug=app.config['DEBUG'],
        host=app.config["FLASK_RUN_HOST"],
        port=app.config["FLASK_RUN_PORT"]
    )
