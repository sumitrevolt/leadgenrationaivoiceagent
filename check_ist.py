from datetime import datetime, timedelta
ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
print(f"IST: {ist.strftime('%Y-%m-%d %H:%M %Z')}")
print(f"Hour: {ist.hour}")
