# Mail Gateway Allowlist Integration

## Overview

TidePool adds a signed `X-TidePool-Campaign-ID` header to every outbound simulation email. This header allows mail security gateways (Mimecast, Microsoft Defender for Office 365, Barracuda, and others) to identify TidePool emails and bypass spam/phishing filters, ensuring simulation messages reach employee inboxes.

The header is cryptographically signed with HMAC-SHA256 using a shared secret. This prevents attackers from forging the header to bypass filters for real phishing emails -- only emails signed with the correct secret will pass verification.

---

## Header Format

```
X-TidePool-Campaign-ID: 42:a1b2c3d4e5f6...
```

Format: `{campaign_id}:{hmac_sha256_hex}`

- **campaign_id**: The numeric campaign identifier (integer).
- **hmac_sha256_hex**: A 64-character hex string produced by HMAC-SHA256 over the campaign_id using the shared secret.

Example with campaign ID 42:

```
X-TidePool-Campaign-ID: 42:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

---

## How It Works

1. When TidePool dispatches an email, it computes `HMAC-SHA256(secret, campaign_id)` and appends the signature to the campaign ID.
2. The signed header is added to the email's SMTP headers before delivery.
3. The receiving mail gateway checks for the `X-TidePool-Campaign-ID` header.
4. If HMAC verification is configured, the gateway recomputes the HMAC and compares it to the signature in the header. If they match, the email is allowed through.
5. If only header-presence checking is configured (simpler but less secure), the gateway allows any email with the header. This approach is acceptable when the SMTP path is trusted end-to-end.

The HMAC prevents:

- **Spoofing**: An attacker cannot produce a valid signature without the shared secret.
- **Cross-campaign replay**: Each campaign ID produces a different signature, so a captured header from campaign 42 cannot be reused for campaign 43.

---

## Configuration in TidePool

### Environment Variables

Add the following to your `.env` file:

```bash
# Campaign header signing (mail gateway allowlisting)
TIDEPOOL_HEADER_ENABLED=true
TIDEPOOL_HEADER_SECRET=your-shared-secret-here
```

### Generating a Strong Secret

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

This produces a 64-character hex string (256 bits of entropy). Share this secret securely with the mail gateway team. Do not transmit it over email or store it in shared documents -- use a secrets manager or encrypted channel.

### Disabling the Header

Set `TIDEPOOL_HEADER_ENABLED=false` to disable header injection. Emails will be sent without the `X-TidePool-Campaign-ID` header.

---

## Example: Content Filter Configuration

These instructions show how to create a content filter rule in a typical mail security gateway to allow TidePool simulation emails to bypass spam and phishing analysis.

### Step 1: Create a Custom Content Filter

1. Log in to your mail gateway admin console.
2. Navigate to the content filter or mail flow rules section.
3. Create a new filter:
   - **Name**: `TidePool Phishing Simulation Allowlist`
   - **Direction**: Inbound
   - **Priority**: Set high priority (low number) so this rule is evaluated before other spam/phishing filters.

### Step 2: Define the Match Condition

1. Add a header match condition.
2. Set:
   - **Header name**: `X-TidePool-Campaign-ID`
   - **Condition**: `exists` (for basic allowlisting) or `matches regex` with pattern `^\d+:[a-f0-9]{64}$` (to validate the format).

### Step 3: Define the Action

1. Configure the action to deliver with the following options:
   - **Skip spam analysis**: Enabled
   - **Skip phishing analysis**: Enabled
   - **Skip impostor/BEC detection**: Enabled (to prevent BEC filters from quarantining the simulation)
2. Optionally, add a tag or log entry for audit purposes.

### Step 4: HMAC Verification (Recommended)

For full cryptographic verification, provide the following Python snippet to your security operations team:

```python
import hmac
import hashlib


def verify_tidepool_header(header_value: str, secret: str) -> bool:
    """
    Verify a TidePool campaign header signature.

    Args:
        header_value: The full X-TidePool-Campaign-ID header value
                      (e.g., "42:e3b0c44298fc...").
        secret: The shared HMAC secret.

    Returns:
        True if the signature is valid, False otherwise.
    """
    try:
        campaign_id, signature = header_value.rsplit(":", 1)
        expected = hmac.new(
            secret.encode(), campaign_id.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected)
    except (ValueError, AttributeError):
        return False
```

If your gateway does not support inline scripts, use the regex-based match condition from Step 2 and rely on the header's existence as sufficient proof. This is secure when the SMTP relay path is controlled (e.g., TidePool sends through a dedicated relay that adds the header, and external senders cannot inject it).

### Step 5: Save and Enable

1. Save the content filter rule.
2. Enable it.
3. Send a test email (see Testing section below) to verify the rule triggers correctly.

---

## Verification Script

Use this standalone script to verify header signatures outside the mail gateway:

```python
#!/usr/bin/env python3
"""Verify a TidePool campaign header signature."""

import hmac
import hashlib
import sys


def verify(header_value: str, secret: str) -> bool:
    """Return True if the HMAC signature in the header is valid."""
    try:
        campaign_id, signature = header_value.rsplit(":", 1)
        expected = hmac.new(
            secret.encode(), campaign_id.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected)
    except (ValueError, AttributeError):
        return False


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 verify_header.py <header_value> <secret>")
        print('Example: python3 verify_header.py "42:e3b0c44..." "your-secret"')
        sys.exit(1)

    header_val = sys.argv[1]
    secret_key = sys.argv[2]

    if verify(header_val, secret_key):
        print("VALID -- signature matches.")
    else:
        print("INVALID -- signature does not match.")
        sys.exit(1)
```

---

## Testing

### Step 1: Send a Test Email via MailHog

With TidePool running in development mode (MailHog as the SMTP backend), create and dispatch a small test campaign. The email will be captured by MailHog.

### Step 2: Inspect the Header in MailHog

```bash
# List recent messages and extract the TidePool header
curl -s http://localhost:8025/api/v2/messages | \
  python3 -c "
import sys, json
messages = json.load(sys.stdin)['items']
for msg in messages[:5]:
    headers = msg['Content']['Headers']
    tp_header = headers.get('X-TidePool-Campaign-ID', ['(not present)'])
    print(f\"To: {msg['Content']['Headers']['To'][0]}\")
    print(f\"X-TidePool-Campaign-ID: {tp_header[0]}\")
    print()
"
```

### Step 3: Verify the Signature

```bash
# Replace with the actual header value and your secret
python3 verify_header.py "42:a1b2c3d4e5f6..." "your-shared-secret-here"
```

---

## Other Mail Gateways

### Mimecast

1. Navigate to **Administration** > **Gateway** > **Policies** > **Content Examination**.
2. Create a new policy:
   - **Condition**: Header `X-TidePool-Campaign-ID` exists.
   - **Action**: Allow delivery, bypass spam/impersonation scanning.
3. Apply to inbound mail flow.

### Microsoft Defender for Office 365

1. Go to **Exchange Admin Center** > **Mail flow** > **Rules**.
2. Create a new rule:
   - **Name**: `TidePool Simulation Allowlist`
   - **Apply this rule if**: A message header includes `X-TidePool-Campaign-ID` matching the pattern `^\d+:[a-f0-9]{64}$`.
   - **Do the following**: Set the Spam Confidence Level (SCL) to `-1` (bypass spam filtering).
3. Set the rule priority high so it is evaluated before other transport rules.
4. Save and enable.

### Barracuda Email Security Gateway

1. Navigate to **Advanced Configuration** > **Custom Header Filters**.
2. Add a rule:
   - **Header**: `X-TidePool-Campaign-ID`
   - **Action**: Exempt from Intent Analysis, Virus Scanning, and Spam Scoring.
3. Save and apply.

### Generic SMTP Gateway

For any gateway that supports header-based rules:

1. Match inbound emails where the `X-TidePool-Campaign-ID` header exists.
2. Optionally validate the format with regex: `^\d+:[a-f0-9]{64}$`.
3. Bypass spam, phishing, and impersonation filters for matching messages.

---

## Security Considerations

### Secret Rotation

Rotate the shared secret periodically (recommended: every 90 days or after personnel changes):

1. Generate a new secret: `python3 -c "import secrets; print(secrets.token_hex(32))"`.
2. Update `TIDEPOOL_HEADER_SECRET` in TidePool's `.env` file.
3. Restart TidePool workers: `docker compose restart worker`.
4. Update the secret in the mail gateway configuration.
5. Verify with a test email before running the next campaign.

During rotation, there is a brief window where in-flight emails signed with the old secret may fail verification. Schedule rotations between campaigns to avoid this.

### Secret Handling

- Never include the secret in email message bodies, subject lines, or template content.
- Do not log the secret or the full header value at INFO level. DEBUG-level logging is acceptable in development only.
- Store the secret in a secrets manager (AWS Secrets Manager, HashiCorp Vault, etc.) in production deployments.
- The `.env` file containing the secret should have restrictive file permissions (`chmod 600 .env`).

### HMAC Properties

- HMAC-SHA256 is a keyed hash function. Without the secret, an attacker cannot produce a valid signature.
- Each campaign ID produces a unique signature. A signature captured from campaign 42 cannot be reused for campaign 43 or any other campaign.
- `hmac.compare_digest()` is used for comparison to prevent timing side-channel attacks.

---

## Known Limitations

### AWS SES Custom Header Restriction

AWS SES's `send_email()` API does not support custom headers. Campaigns routed through SES using this API method will not include the `X-TidePool-Campaign-ID` header.

**Workaround**: Switch to the `send_raw_email()` API, which accepts fully formed MIME messages with arbitrary headers. This is a planned enhancement. Until implemented, SES-routed campaigns cannot be allowlisted via the header mechanism.

For SES-routed campaigns in the interim, use IP-based allowlisting (add the SES sending IP range to the mail gateway allowlist) or configure a dedicated SES configuration set with a sending identity that the mail gateway trusts.
