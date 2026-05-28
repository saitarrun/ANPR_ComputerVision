output "vpc_id" {
  value = aws_vpc.main.id
}

output "vpc_cidr" {
  value = aws_vpc.main.cidr_block
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "availability_zones" {
  value = var.availability_zones
}

output "nat_gateway_ips" {
  value = aws_eip.nat[*].public_ip
}

output "internet_gateway_id" {
  value = aws_internet_gateway.main.id
}
