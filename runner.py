import csv
import datetime
import os

from agents.failure_analyzer import FailureAnalyzer

print("Starting Runner...")

analyzer = FailureAnalyzer()

try:
    import tests.test_failure_demo as demo

    print("Executing test...")

    demo.test_login()

except Exception as e:
    print("Exception Caught")

    result = analyzer.analyze(str(e))

    print("\n=== AI Failure Analysis ===")
    print(f"Category: {result['category']}")
    print(f"Root Cause: {result['root_cause']}")
    print(f"Recommendation: {result['recommendation']}")

    os.makedirs("reports", exist_ok=True)

    with open(
        "reports/healing_report.csv",
        "a",
        newline=""
    ) as file:
        writer = csv.writer(file)
        writer.writerow([
            datetime.datetime.now(),
            "test_login",
            str(e),
            result["category"],
            result["recommendation"]
        ])

    print("\nHealing report generated successfully.")
