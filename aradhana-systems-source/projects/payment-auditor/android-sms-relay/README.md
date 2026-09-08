# Aradhana SMS Relay

Rootless Android companion for the Aradhana Payment Auditor. It forwards only SMS messages from an explicit bank-sender whitelist through your SMTP account to the Auditor mailbox.

## Security model

- No root, paid relay service, analytics SDK or external API.
- SMTP password and relay configuration are stored using Android Keystore-backed encrypted preferences.
- Default: a sender whitelist is mandatory. No whitelist means no SMS forwarding.
- Optional, explicit **Forward every incoming SMS** mode bypasses the sender whitelist. It forwards OTPs and personal messages too; enable only on a dedicated, controlled bank-SIM phone.
- Duplicate SMS content from the same sender is suppressed for 14 days.
- Mail subjects use `[SMSForwarder]`, which the existing Auditor email poller recognizes.

## Build

Requires Android Studio with JDK 17 and Android SDK Platform 35.

1. Open this `android-sms-relay` folder in Android Studio.
2. Wait for Gradle sync.
3. Connect the relay phone by USB with USB debugging enabled, or use Android Studio's device manager.
4. Run the `app` configuration, or use `Build > Build APK(s)`.
5. Install only the generated APK on the dedicated bank-SMS phone.

## Configure

1. Grant SMS permission.
2. Set the phone's Battery usage for this app to **Unrestricted** and allow Auto-start / Background activity.
3. Use a dedicated Gmail sender account with a Google App Password:
   - SMTP host: `smtp.gmail.com`
   - SMTP port: `465`
4. Recipient: the mailbox polled by Aradhana Payment Auditor.
5. Add actual bank sender IDs from the relay phone's SMS inbox, one per line. Use `AX-*` only where a bank rotates its sender suffix. Or explicitly enable **Forward every incoming SMS**.
6. Save and send the safe test email.

## Auditor integration

The email body begins `From : <sender>` and the subject begins `[SMSForwarder]`. `backend/email_poller.py` classifies it as `SMS_FORWARDER`, creates `SMSAlert` and a deduplicated `BankAlert`, then passes it to reconciliation.

## Operational rule

Use a spare, PIN-protected Android phone dedicated to bank SIMs. Do not whitelist generic sender IDs that may carry password-reset or personal messages.
