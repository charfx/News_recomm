import sys
from getpass import getpass

from Backend.app.DB import SessionLocal
from Backend.app.Models import User
from Backend.app.auth import hash_password


def main():
    email = (sys.argv[1] if len(sys.argv) > 1 else input("Email admin : ")).strip().lower()
    password = getpass("Mot de passe admin : ")
    if len(password) < 6:
        sys.exit("Mot de passe trop court")

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=email).first()
        if user:                                   # compte existant → promu admin
            user.role = "admin"
            user.password_hash = hash_password(password)
        else:
            user = User(email=email, password_hash=hash_password(password), role="admin")
            db.add(user)
        db.commit()
        print(f"OK : {email} est admin (id={user.id})")
    finally:
        db.close()


if __name__ == "__main__":
    main()