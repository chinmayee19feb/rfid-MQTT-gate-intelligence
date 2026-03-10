output "rfid_events_table_name" {
  description = "DynamoDB table name for RFID tag events"
  value       = aws_dynamodb_table.rfid_events.name
}

output "health_events_table_name" {
  description = "DynamoDB table name for health status packets"
  value       = aws_dynamodb_table.health_events.name
}

output "rfid_events_table_arn" {
  description = "ARN of RFID events table"
  value       = aws_dynamodb_table.rfid_events.arn
}