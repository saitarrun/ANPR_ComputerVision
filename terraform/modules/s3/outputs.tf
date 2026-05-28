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
