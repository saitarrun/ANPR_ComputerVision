output "s3_bucket_frames_id" {
  value = aws_s3_bucket.main["frames"].id
}

output "s3_bucket_crops_id" {
  value = aws_s3_bucket.main["crops"].id
}

output "s3_bucket_audit_id" {
  value = aws_s3_bucket.main["audit"].id
}

output "s3_kms_key_id" {
  value = aws_kms_key.s3.key_id
}

output "fastapi_s3_role_arn" {
  value       = aws_iam_role.fastapi_s3_access.arn
  description = "IAM role for FastAPI service (read frames, write crops)"
}

output "celery_s3_role_arn" {
  value       = aws_iam_role.celery_s3_access.arn
  description = "IAM role for Celery workers (write crops only)"
}

output "audit_s3_role_arn" {
  value       = aws_iam_role.audit_s3_access.arn
  description = "IAM role for audit logging (write audit logs only)"
}
