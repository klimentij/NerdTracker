#!/usr/bin/env python3

import json
import secrets
import string
from pathlib import Path
import urllib.request
import urllib.error
import urllib.parse

def generate_secret(length: int) -> str:
    """Generate a random string of specified length."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def update_json_file(file_path: Path, updates: dict) -> None:
    """Update JSON file with new values."""
    if not file_path.exists():
        print(f"Error: {file_path} not found!")
        return
    
    with open(file_path) as f:
        data = json.load(f)
    
    data.update(updates)
    
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)

def main():
    print("\n=== Welcome to the Setup Script ===")
    print("This will help you configure your application secrets\n")

    # Get Supabase credentials
    supabase_url = input("Please enter your Supabase Project URL: ")
    anon_key = input("Please enter your Supabase Anon/Public Key: ")

    # Generate secrets
    print("\nGenerating secure secrets...")
    secrets_dict = {
        "jwt_secret": generate_secret(32),
        "magic_link_secret": generate_secret(32),
        "auth_password": generate_secret(32),
        "location_inserter_password": generate_secret(8)
    }

    # Update app/secrets.json
    app_secrets = Path("app/secrets.json")
    app_dist = Path("app/secrets.dist.json")
    if not app_secrets.exists():
        print("Creating app/secrets.json from template...")
        app_secrets.write_text(app_dist.read_text())

    app_updates = {
        "SUPABASE_URL": supabase_url,
        "SUPABASE_KEY": anon_key,
        "AUTH_PASSWORD": secrets_dict["auth_password"],
        "JWT_SECRET": secrets_dict["jwt_secret"],
        "MAGIC_LINK_SECRET": secrets_dict["magic_link_secret"]
    }
    update_json_file(app_secrets, app_updates)

    # Update location-inserter/secrets.json
    inserter_secrets = Path("location-inserter/secrets.json")
    inserter_dist = Path("location-inserter/secrets.dist.json")
    if not inserter_secrets.exists():
        print("Creating location-inserter/secrets.json from template...")
        inserter_secrets.write_text(inserter_dist.read_text())

    inserter_updates = {
        "SUPABASE_URL": supabase_url,
        "SUPABASE_KEY": anon_key,
        "AUTH_USER": "admin",
        "AUTH_PASS": secrets_dict["location_inserter_password"]
    }
    update_json_file(inserter_secrets, inserter_updates)

    # Display results
    print("\nSetup complete! 🎉")
    print("\nGenerated passwords:")
    print("=" * 40)
    print(f"App AUTH_PASSWORD: {secrets_dict['auth_password']}")
    print(f"Location Inserter password: {secrets_dict['location_inserter_password']}")
    print("=" * 40)
    print("SAVE THESE SOMEWHERE SAFE!")
    
    print("\nOwnTracks App Settings:")
    print("=" * 40)
    print(f"UserID: admin")
    print(f"Password: {secrets_dict['location_inserter_password']}")
    print("=" * 40)
    print("\nIMPORTANT: Please execute the SQL commands from the README.md in your Supabase dashboard!")

if __name__ == "__main__":
    main()
