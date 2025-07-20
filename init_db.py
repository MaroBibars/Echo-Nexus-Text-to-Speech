from text_to_speech import app, db

with app.app_context():
    db.create_all()
    print("Database initialized!")