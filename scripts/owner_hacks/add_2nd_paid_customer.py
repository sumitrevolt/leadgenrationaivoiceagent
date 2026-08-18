import asyncio
import json
from datetime import datetime, timezone

from app.api import upi_payments as api_upi
from app.platform import upi_payments


def run():
    # Add pending payment
    submit_req = api_upi.UPISubmitRequest(
        client_id="2nd_paid_customer",
        tenant_id="2nd_paid_customer",
        plan_key="leadgen_marketing_pro",
        phone="9988776655",  # sample phone
        transaction_id="TXN123456789",
        amount_inr=5999.0,
    )

    res = upi_payments.record_submission(
        client_id=submit_req.client_id,
        plan_key=submit_req.plan_key,
        phone=submit_req.phone,
        transaction_id=submit_req.transaction_id,
        amount_inr=submit_req.amount_inr,
        tenant_id=submit_req.tenant_id,
    )

    sub_id = res["id"]
    print("Created pending UPI:", sub_id)

    # Approve it!
    approve_req = api_upi.UPIApproveRequest(submission_id=sub_id, action="approve")
    api_res = asyncio.run(api_upi._process_action(approve_req))
    print("Activated!", api_res)


if __name__ == "__main__":
    run()
