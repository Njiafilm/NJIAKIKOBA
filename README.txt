NJIAKIKOBA - FINAL ALL-IN-ONE PACKAGE

Main app: app.py
Templates: templates/
Static CSS: static/style.css

Included:
- Multi-group registration and group isolation
- Maximum 999 members per group
- Up to 3 leaders per group
- Private Developer Room / inspection
- Developer excluded from member groups and member-visible chat
- Group-specific WhatsApp member list
- Group chat media support (image/audio/video)
- Video/conference call templates
- Savings, loan, repayment and payment workflow code
- Payment/webhook safety and transaction records

Before production:
1. Configure BLMPay/API credentials and callback URL in environment variables.
2. Use a persistent production database (PostgreSQL recommended) instead of SQLite for concurrent registrations/payments.
3. Configure HTTPS and the production Jitsi/video provider as required.
4. Review all environment secrets before deployment.


NEW DEVELOPER TOOLS
- Payment Systems: Developer Room now has no-code provider configuration for Azam Pay, Click Pesa, BLMPay and other HTTPS API providers. Fill Base URL, API key/secret, merchant ID, collection/payout/webhook paths and enable. Connectivity Test NEVER sends a real payment.
- System Error Repair Center: Developer can paste an error description and generate a deterministic safe repair plan. Apply Safe Fix only performs known non-destructive database migration/refresh actions; it never exec()s arbitrary generated code or rewrites app.py automatically.
- For real provider integration, endpoint semantics vary by provider. The provider's official API documentation/credentials are still required; this UI stores the configuration without editing Python code.
