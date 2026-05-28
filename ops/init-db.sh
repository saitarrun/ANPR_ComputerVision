#!/bin/bash
# Initialize ANPR database and create application user

set -e

POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-postgres}
DB_NAME=${DB_NAME:-anpr_db}
APP_USER=${APP_USER:-anpr}
APP_PASSWORD=${APP_PASSWORD:-anpr_dev_pw}

echo "Initializing ANPR database..."

# Create application user if not exists
psql -v ON_ERROR_STOP=1 <<-EOSQL
    -- Create application user
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_user WHERE usename = '$APP_USER') THEN
            CREATE USER $APP_USER WITH PASSWORD '$APP_PASSWORD';
        END IF;
    END
    \$\$;

    -- Grant privileges
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $APP_USER;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $APP_USER;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO $APP_USER;

    -- Grant existing objects
    GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $APP_USER;
    GRANT ALL PRIVILEGES ON SCHEMA public TO $APP_USER;
    GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO $APP_USER;
    GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO $APP_USER;
    GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO $APP_USER;
EOSQL

echo "✓ Database initialized successfully"
echo "  User: $APP_USER"
echo "  Database: $DB_NAME"
