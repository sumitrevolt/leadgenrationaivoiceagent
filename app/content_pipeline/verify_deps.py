import os
import sys

# Ensure dependencies are available (referring to main requirements logic)
# This script must be run via the project's env venv
def verify_env():
    try:
        import edge_tts
        import groq
        print("Dependencies found.")
    except ImportError as e:
        print(f"Error: {e}")
        print("Please ensure you are running this from the project virtual environment.")
        sys.exit(1)

if __name__ == "__main__":
    verify_env()
