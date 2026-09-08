import re

filepath = r"C:\Users\kaila\aradhana-payment-auditor\aradhana-payment-auditor\backend\review_api.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace("PaymentModel.is_test_data == False,\n", "")

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Removed PaymentModel.is_test_data == False")
