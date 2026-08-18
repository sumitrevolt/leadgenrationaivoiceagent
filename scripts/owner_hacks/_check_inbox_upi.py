from app.platform import inbox_frontend, upi_payments


def run():
    stats = inbox_frontend.get_hq_summary("boss")
    print("--- HOT QUEUE ---")
    print(stats)

    pending = upi_payments.list_state("pending")
    print("--- PENDING UPI ---")
    for p in pending:
        print(f"ID: {p['id']}, Phone: {p.get('phone')}, Tx: {p.get('transaction_id')}")


if __name__ == "__main__":
    run()
