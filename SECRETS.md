# Secrets Management

## Setup (Local Dev)

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Fill in values from your secrets manager (AWS Secrets Manager, HashiCorp Vault, 1Password, etc.):
   ```bash
   export AWS_REGION=us-east-1
   # Retrieve from AWS Secrets Manager / Vault / etc.
   ```

3. Generate encryption keys if needed:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

4. **Never commit `.env` to git** — it is in `.gitignore`.

## CI/CD (GitHub Actions)

In your CI/CD pipeline, set secrets as environment variables or fetch from a secret store:
```yaml
- name: Run tests
  env:
    POSTGRES_PASSWORD: ${{ secrets.POSTGRES_PASSWORD }}
    JWT_SECRET: ${{ secrets.JWT_SECRET }}
  run: pytest tests/ -v
```

## Production Migration (Post-M6)

After M6, integrate with:
- **AWS Secrets Manager**: Fetch secrets at runtime via boto3
- **HashiCorp Vault**: Use Vault agent or direct client
- **Azure Key Vault**: Use `azure-keyvault-secrets` SDK

This avoids storing plaintext `.env` files on production instances.

## Rotating Secrets

1. Create new secret in your vault
2. Update environment variable
3. Redeploy / restart service
4. Delete old secret

(Implement rotation scripts post-M6)

## Checklist

- [ ] `.env` is **not** committed to git
- [ ] `.env.example` has placeholders only (no real values)
- [ ] Tests use `os.getenv()` with defaults or required env vars
- [ ] CI/CD pipeline injects secrets via environment or secret manager
- [ ] Production deployment fetches from vault (post-M6)
