import asyncio

from app.billing.paid_activations import daily_paid_activations
from app.platform.upi_payments import list_payments


def check_sync():
    actionable = list_payments()
    for row in actionable:
        print(row)
    print("Total queue size:", len(actionable))


if __name__ == "__main__":
    check_sync()
