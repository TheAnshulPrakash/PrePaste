from presidio_analyzer import AnalyzerEngine

print("Loading Presidio models...")
analyzer = AnalyzerEngine()

# 2. Sample data: A block of text containing some PII
sample_data = """
# Sample PII Data for Testing

This file contains various types of PII data that can be detected by the PII scanner.

## Personal Information

Name: John Doe
Email: john.doe@example.com
Phone: (555) 123-4567
Address: 123 Main St, Boston, MA 02115
Date of Birth: 01/01/1980
SSN: 123-45-6789
Harvard ID: 12345678

## Financial Information

Credit Card: 4111 1111 1111 1111
Expiration: 12/25
CVV: 123
Bank Account: 123456789
Routing Number: 021000021

## Credentials

Username: johndoe
Password: P@ssw0rd123!
API Key: api_key="abcdef123456789"
AWS Access Key: AKIAIOSFODNN7EXAMPLE
AWS Secret Key: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY

## Database Connection Strings

MongoDB: mongodb://user:password@mongodb0.example.com:27017/admin
PostgreSQL: postgresql://user:password@localhost:5432/mydb
MySQL: mysql://user:password@localhost:3306/mydb

## Other Sensitive Information

IP Address: 192.168.1.1
MAC Address: 00:11:22:33:44:55
Bearer Token: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c
"""

print("\n--- Starting Scan ---\n")

# 3. Split the text into lines and track the line number
# enumerate(..., start=1) makes our line numbers start at 1 instead of 0
lines = sample_data.split("\n")

for line_number, line_text in enumerate(lines, start=1):

    # Skip completely empty lines to save processing time
    if not line_text.strip():
        continue

    # Analyze the specific line for PII in English
    results = analyzer.analyze(text=line_text, language="en")

    # 4. Check if any PII was found on this line
    if results:
        # Loop through everything Presidio found on this specific line
        for result in results:
            # Presidio returns the start and end index.
            # We use them to slice the exact word out of the line.
            extracted_pii = line_text[result.start : result.end]

            print(
                f"Line {line_number} | Type: {result.entity_type} | Text: '{extracted_pii}' | Confidence: {result.score:.2f}"
            )
    else:
        # Optional: Print clean lines if you want a full audit log
        print(f"Line {line_number} | Clean")

print("\n--- Scan Complete ---")
