"""Give a Firebase user the custom claim {admin: true}.

    python -m library.set_admin <uid>

Needs GOOGLE_APPLICATION_CREDENTIALS. The user must sign in again (or refresh their
ID token) before the claim shows up.
"""
import sys


def set_admin(uid: str) -> None:
    import firebase_admin
    from firebase_admin import auth

    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    auth.set_custom_user_claims(uid, {"admin": True})


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m library.set_admin <uid>")
    set_admin(sys.argv[1])
    print(f"admin claim set for {sys.argv[1]}")
