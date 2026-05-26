# Security Policy

## Supported Versions

This project is currently maintained on the `main` branch.

| Version / Branch | Supported |
| --- | --- |
| main | Yes |

## Reporting a Vulnerability

If you discover a security vulnerability, please do not open a public issue.

Please contact the repository owner privately and include:

- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested mitigation, if available

Sensitive credentials, API keys, tokens, private datasets, trading records, or personal data should never be posted publicly.

## Secret Handling

This project must not commit secrets to the repository, including:

- API keys
- Access tokens
- Passwords
- `.env` files
- `.streamlit/secrets.toml`
- Private keys or certificate files

If a secret is accidentally exposed, revoke it immediately and create a new one from the provider dashboard.
