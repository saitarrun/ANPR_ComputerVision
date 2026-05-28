# Quick Reference: Local Dev Environment

## One-Time Setup
```bash
make dev-setup                # Install deps + start services + seed DB (30 sec)
```

## Daily Workflow
```bash
# Morning: Start services
make dev-up                   # Start all services

# During dev: Follow logs
make dev-logs                 # Tail all logs
make dev-logs-api             # API only
make dev-logs-worker          # Worker only

# Code → hot-reload happens automatically

# Run tests as you code
make test                     # All tests
make test-unit                # Unit tests
make test-int                 # Integration tests
make test-watch               # Auto-rerun on changes

# End of day
make dev-down                 # Stop services (keep data)
```

## Code Quality
```bash
make fmt                      # Auto-format code
make lint                     # Check code quality
make fmt && make lint         # Both
```

## Database
```bash
make psql                     # PostgreSQL CLI
make db-migrate               # Run migrations
make db-seed                  # Seed test data
make dev-reset                # [DESTRUCTIVE] Drop all, recreate
```

## Cache Inspection
```bash
make redis-cli                # Redis CLI
make health                   # Check service health
```

## Service URLs
| Service | URL |
|---------|-----|
| API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| pgAdmin | http://localhost:5050 |
| Redis Commander | http://localhost:8081 |
| MinIO Console | http://localhost:9001 |

## Test Credentials
```
Email:    test@example.com
Password: password123
```

## Troubleshooting
```bash
docker-compose ps            # Check service status
docker-compose logs api      # See API logs
docker-compose restart api   # Restart API
docker-compose down -v       # Full reset (deletes data)
docker system prune -a       # Clean up Docker
```

## All Make Targets
```bash
make help                     # Show all commands
```

## Environment
```bash
cat .env.local                # View current secrets
# Edit for local overrides
```

## See Also
- `DEV_ENVIRONMENT.md` — Service endpoints & quick start
- `LOCAL_SETUP.md` — Full setup guide + troubleshooting
- `DOCKER_TROUBLESHOOTING.md` — Docker issues & solutions
- `Makefile.dev` — All 40+ make targets
