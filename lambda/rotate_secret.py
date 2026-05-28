"""
AWS Lambda function for automatic RDS password rotation via Secrets Manager.

Handles the 4-step rotation lifecycle:
1. create: Generate new password
2. set: Update RDS master password
3. test: Verify connection with new password
4. finish: Finalize rotation in Secrets Manager

Triggered by AWS Secrets Manager rotation events.
"""

import json
import logging
import os
import secrets
import string
from datetime import datetime

import boto3
import psycopg2
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# AWS clients
secrets_client = boto3.client("secretsmanager")
rds_client = boto3.client("rds")


def lambda_handler(event, context):
    """
    Main Lambda handler for secrets rotation.

    Args:
        event: Secrets Manager rotation event with:
            - SecretId: ARN or name of secret being rotated
            - ClientRequestToken: Unique request ID
            - Step: 'create', 'set', 'test', or 'finish'
        context: Lambda context object

    Returns:
        dict: Success response with rotation metadata
    """
    secret_id = event["SecretId"]
    client_request_token = event["ClientRequestToken"]
    step = event["Step"]
    secret_version_stage = event.get("SecretVersionStage", "AWSPENDING")

    logger.info(
        f"Starting rotation step '{step}' for secret {secret_id} "
        f"with token {client_request_token}"
    )

    # Get secret metadata
    try:
        secret = secrets_client.describe_secret(SecretId=secret_id)
    except ClientError as e:
        logger.error(f"Failed to describe secret {secret_id}: {e}")
        raise

    # Validate secret is configured for rotation
    if "RotationRules" not in secret:
        raise ValueError(f"Secret {secret_id} is not configured for rotation")

    # Get current secret version to extract DB connection details
    try:
        current_secret = secrets_client.get_secret_value(
            SecretId=secret_id, VersionStage="AWSCURRENT"
        )
        current_dict = json.loads(current_secret["SecretString"])
    except ClientError as e:
        logger.error(f"Failed to get current secret value: {e}")
        raise

    # Extract RDS instance identifier from metadata tags or secret
    rds_instance_id = os.environ.get("RDS_INSTANCE_ID")
    if not rds_instance_id:
        # Fallback: try to extract from secret metadata
        secret_tags = {tag["Key"]: tag["Value"] for tag in secret.get("Tags", [])}
        rds_instance_id = secret_tags.get("rds_instance_id")

    if not rds_instance_id:
        raise ValueError(
            "RDS_INSTANCE_ID not found in environment or secret tags. "
            "Cannot determine target database instance."
        )

    logger.info(f"Target RDS instance: {rds_instance_id}")

    try:
        if step == "create":
            create_secret(secret_id, client_request_token, rds_instance_id)

        elif step == "set":
            set_secret(
                secret_id,
                client_request_token,
                current_dict,
                rds_instance_id,
                secret_version_stage,
            )

        elif step == "test":
            test_secret(secret_id, client_request_token, current_dict, rds_instance_id)

        elif step == "finish":
            finish_secret(secret_id, client_request_token)

        else:
            raise ValueError(f"Invalid step: {step}")

        logger.info(f"Rotation step '{step}' completed successfully")
        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": f"Rotation step '{step}' completed",
                    "secret_id": secret_id,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            ),
        }

    except Exception as e:
        logger.error(f"Rotation failed at step '{step}': {str(e)}", exc_info=True)
        # Attempt to log rotation failure to CloudWatch for monitoring
        log_rotation_failure(secret_id, step, str(e))
        raise


def create_secret(secret_id: str, client_request_token: str, rds_instance_id: str):
    """
    Step 1: Generate new password and store in AWSPENDING version.

    Creates a 32-character password with uppercase, lowercase, numbers, and symbols.
    Stores it as a new secret version with AWSPENDING stage.

    Args:
        secret_id: Secret ARN or name
        client_request_token: Unique token for this rotation
        rds_instance_id: RDS instance identifier
    """
    # Generate strong password: 32 chars with mixed character classes
    # Avoid problematic characters like @ and ' to prevent RDS/psql issues
    alphabet = string.ascii_letters + string.digits + "!#$%&*+,-./:<=>?_`~"
    new_password = "".join(secrets.choice(alphabet) for _ in range(32))

    # Verify password meets RDS requirements
    if not validate_password(new_password):
        raise ValueError("Generated password failed validation")

    logger.info(f"Generated new password for secret {secret_id}")

    try:
        # Get current secret to preserve other fields
        current_secret = secrets_client.get_secret_value(
            SecretId=secret_id, VersionStage="AWSCURRENT"
        )
        current_dict = json.loads(current_secret["SecretString"])

        # Create new version with updated password
        new_dict = current_dict.copy()
        new_dict["password"] = new_password

        # Put new secret version with AWSPENDING stage
        secrets_client.put_secret_value(
            SecretId=secret_id,
            ClientRequestToken=client_request_token,
            SecretString=json.dumps(new_dict),
            VersionStages=["AWSPENDING"],
        )

        logger.info(
            f"Created AWSPENDING version {client_request_token} for secret {secret_id}"
        )

    except ClientError as e:
        logger.error(f"Failed to create secret version: {e}")
        raise


def set_secret(
    secret_id: str,
    client_request_token: str,
    current_secret: dict,
    rds_instance_id: str,
    secret_version_stage: str,
):
    """
    Step 2: Update RDS master password with new password.

    Retrieves the AWSPENDING secret version and applies the new password
    to the RDS master user via ModifyDBInstance API.

    Args:
        secret_id: Secret ARN or name
        client_request_token: Unique token for this rotation
        current_secret: Current secret dict (with old password)
        rds_instance_id: RDS instance identifier
        secret_version_stage: Version stage (typically AWSPENDING)
    """
    try:
        # Get the new secret (AWSPENDING version with new password)
        pending_secret = secrets_client.get_secret_value(
            SecretId=secret_id, VersionId=client_request_token
        )
        pending_dict = json.loads(pending_secret["SecretString"])
        new_password = pending_dict["password"]
        master_username = pending_dict.get("username", current_secret.get("username"))

        logger.info(
            f"Updating RDS master password for {rds_instance_id} "
            f"user {master_username}"
        )

        # Update RDS master password (idempotent with retries)
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                rds_client.modify_db_instance(
                    DBInstanceIdentifier=rds_instance_id,
                    MasterUserPassword=new_password,
                    ApplyImmediately=True,
                )
                logger.info(f"Successfully updated RDS password for {rds_instance_id}")
                break

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                if error_code in [
                    "InvalidDBInstanceState",
                    "DBInstanceNotFound",
                ] and attempt < max_retries:
                    # Transient error, retry after exponential backoff
                    backoff_seconds = 2**attempt
                    logger.warning(
                        f"Transient RDS error ({error_code}), retrying in "
                        f"{backoff_seconds}s (attempt {attempt}/{max_retries})"
                    )
                    import time

                    time.sleep(backoff_seconds)
                else:
                    logger.error(
                        f"Failed to update RDS password (attempt {attempt}): {e}"
                    )
                    raise

    except ClientError as e:
        logger.error(f"Failed to get pending secret or update RDS: {e}")
        raise


def test_secret(
    secret_id: str,
    client_request_token: str,
    current_secret: dict,
    rds_instance_id: str,
):
    """
    Step 3: Test connection with new password.

    Retrieves the AWSPENDING secret version and attempts to establish
    a PostgreSQL connection to verify the new password works.

    Args:
        secret_id: Secret ARN or name
        client_request_token: Unique token for this rotation
        current_secret: Current secret dict (fallback)
        rds_instance_id: RDS instance identifier

    Raises:
        Exception: If connection test fails
    """
    try:
        # Get the new secret (AWSPENDING version)
        pending_secret = secrets_client.get_secret_value(
            SecretId=secret_id, VersionId=client_request_token
        )
        pending_dict = json.loads(pending_secret["SecretString"])

        # Get RDS instance endpoint
        db_instance = rds_client.describe_db_instances(
            DBInstanceIdentifier=rds_instance_id
        )
        if not db_instance["DBInstances"]:
            raise ValueError(f"RDS instance {rds_instance_id} not found")

        endpoint = db_instance["DBInstances"][0]["Endpoint"]
        host = endpoint["Address"]
        port = endpoint.get("Port", 5432)

        # Extract connection parameters from secret
        username = pending_dict.get("username")
        password = pending_dict.get("password")
        dbname = pending_dict.get("dbname", "postgres")

        logger.info(f"Testing connection to {host}:{port} as {username}")

        # Attempt connection with exponential backoff for transient failures
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                conn = psycopg2.connect(
                    host=host,
                    port=port,
                    user=username,
                    password=password,
                    database=dbname,
                    connect_timeout=10,
                    sslmode="require",
                )
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                conn.close()

                logger.info(f"Successfully tested connection to {rds_instance_id}")
                return

            except psycopg2.OperationalError as e:
                if attempt < max_retries:
                    backoff_seconds = 2**attempt
                    logger.warning(
                        f"Connection test failed, retrying in {backoff_seconds}s "
                        f"(attempt {attempt}/{max_retries}): {e}"
                    )
                    import time

                    time.sleep(backoff_seconds)
                else:
                    logger.error(f"Connection test failed after {max_retries} attempts")
                    raise

    except Exception as e:
        logger.error(f"Failed to test secret connection: {e}", exc_info=True)
        raise


def finish_secret(secret_id: str, client_request_token: str):
    """
    Step 4: Finalize rotation by moving AWSPENDING to AWSCURRENT.

    Updates the Secrets Manager version stages to promote the rotated
    secret from AWSPENDING to AWSCURRENT and remove the old version.

    Args:
        secret_id: Secret ARN or name
        client_request_token: Unique token for this rotation
    """
    try:
        # Get current metadata
        metadata = secrets_client.describe_secret(SecretId=secret_id)

        # Find old current version to remove AWSCURRENT stage
        current_version = None
        for version in metadata["VersionIdsToStages"]:
            if "AWSCURRENT" in metadata["VersionIdsToStages"][version]:
                current_version = version
                break

        # Update version stages: promote AWSPENDING to AWSCURRENT
        if current_version:
            logger.info(
                f"Moving AWSCURRENT stage from {current_version} to "
                f"{client_request_token}"
            )
            secrets_client.update_secret_version_stage(
                SecretId=secret_id,
                VersionStage="AWSCURRENT",
                MoveToVersionId=client_request_token,
                RemoveFromVersionId=current_version,
            )
        else:
            logger.warning(
                "No current version found, adding AWSCURRENT to pending version"
            )
            secrets_client.update_secret_version_stage(
                SecretId=secret_id,
                VersionStage="AWSCURRENT",
                MoveToVersionId=client_request_token,
            )

        logger.info(f"Successfully finalized rotation for secret {secret_id}")

    except ClientError as e:
        logger.error(f"Failed to finalize rotation: {e}")
        raise


def validate_password(password: str) -> bool:
    """
    Validate password meets AWS RDS requirements.

    RDS PostgreSQL password requirements:
    - 8 to 128 characters
    - Can include letters, numbers, special chars
    - Cannot contain forward slash, double quote, or backslash

    Args:
        password: Password to validate

    Returns:
        bool: True if valid, False otherwise
    """
    if not (8 <= len(password) <= 128):
        logger.error(f"Password length invalid: {len(password)}")
        return False

    forbidden = ['/', '"', "\\", "@"]
    if any(char in password for char in forbidden):
        logger.error("Password contains forbidden characters")
        return False

    return True


def log_rotation_failure(secret_id: str, step: str, error_message: str):
    """
    Log rotation failure to CloudWatch for alerting.

    Args:
        secret_id: Secret ARN or name
        step: Rotation step where failure occurred
        error_message: Error message
    """
    try:
        cloudwatch = boto3.client("logs")
        log_group = f"/aws/lambda/secrets-rotation/{secret_id.split('/')[-1]}"
        log_stream = f"rotation-failures-{datetime.utcnow().strftime('%Y-%m-%d')}"

        # Create log group if it doesn't exist
        try:
            cloudwatch.create_log_group(logGroupName=log_group)
        except cloudwatch.exceptions.ResourceAlreadyExistsException:
            pass

        # Create log stream if it doesn't exist
        try:
            cloudwatch.create_log_stream(
                logGroupName=log_group, logStreamName=log_stream
            )
        except cloudwatch.exceptions.ResourceAlreadyExistsException:
            pass

        # Log the failure event
        cloudwatch.put_log_events(
            logGroupName=log_group,
            logStreamName=log_stream,
            logEvents=[
                {
                    "timestamp": int(datetime.utcnow().timestamp() * 1000),
                    "message": json.dumps(
                        {
                            "event": "rotation_failure",
                            "secret_id": secret_id,
                            "step": step,
                            "error": error_message,
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    ),
                }
            ],
        )
    except Exception as e:
        logger.warning(f"Failed to log rotation failure to CloudWatch: {e}")
