#!/usr/bin/env python3
"""
Section 22: 50 Paid Customers/Day Target Calculator
Calculates required throughput, extrapolating from existing rates.
"""


def calculate_funnel(target_paid: int = 50):
    print("=========================================")
    print(f" REVENUE FUNNEL TARGET: {target_paid} PAID / DAY")
    print("=========================================")

    # Heuristics based on real B2B local business performance expectations
    payment_conv_rate = 0.05  # 5% of offers result in payment
    offer_qualified_rate = 0.50  # 50% of meaningful conversations qualify for offer
    meaningful_conv_rate = 0.10  # 10% of answered calls = meaningful
    answer_rate = 0.35  # 35% answer rate

    offers_needed = target_paid / payment_conv_rate
    meaningful_conv_needed = offers_needed / offer_qualified_rate
    answers_needed = meaningful_conv_needed / meaningful_conv_rate
    calls_needed = answers_needed / answer_rate

    print("Assuming:")
    print(f"  - Answer rate: {answer_rate*100}%")
    print(f"  - Meaningful conversion: {meaningful_conv_rate*100}%")
    print(f"  - Qualify rate: {offer_qualified_rate*100}%")
    print(f"  - Payment conv rate: {payment_conv_rate*100}%")
    print("-----------------------------------------")
    print(f"To get {target_paid} paid customers/day, you need:")
    print(f"  - Offers made: {int(offers_needed)}")
    print(f"  - Meaningful Conversations: {int(meaningful_conv_needed)}")
    print(f"  - Answered Calls: {int(answers_needed)}")
    print(f"  - Total Call Attempts: {int(calls_needed)}")
    print("-----------------------------------------")
    print("INFRASTRUCTURE CAPACITY CALC:")
    call_duration_mins_avg = 3
    daily_call_window_hours = 9  # 10am to 7pm (TRAI rules)
    total_minutes_needed = (
        answers_needed * call_duration_mins_avg + (calls_needed - answers_needed) * 0.5
    )
    concurrency_needed = total_minutes_needed / (daily_call_window_hours * 60)
    print(f"  - Total Daily Call Minutes: {int(total_minutes_needed)} mins")
    print(f"  - Required Vobiz Trunk Concurrency: {int(concurrency_needed + 1)} parallel channels")
    print("  - Current max daily call cap via PLATFORM_DIAL_LIMIT: 100")
    print(f"  - GAP: {int(calls_needed - 100)} calls short of goal.")
    print("=========================================")


if __name__ == "__main__":
    calculate_funnel()
