# ============================================================
# DYNAMODB MODULE
# Stores every RFID tag scan event from the gate readers
# DynamoDB is a key-value / document database (like MongoDB)
# but fully managed by AWS - no server to maintain
# ============================================================

resource "aws_dynamodb_table" "rfid_events" {
  name         = "${var.project_name}-rfid-events"
  billing_mode = "PAY_PER_REQUEST"  # Free tier - only pay per read/write
  hash_key     = "gate_reader_id"   # Partition key - how data is distributed
  range_key    = "timestamp"        # Sort key - orders records within a partition

  # These are the only attributes you MUST define upfront
  # (the ones used as keys). All other fields are flexible.
  attribute {
    name = "gate_reader_id"
    type = "S"              # S = String
  }

  attribute {
    name = "timestamp"
    type = "S"              # S = String (stored as epoch ms string)
  }

  # Keep deleted items recoverable for 35 days
  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name        = "${var.project_name}-rfid-events"
    Environment = var.environment
  }
}

# ============================================================
# SECOND TABLE - Health Status packets
# Stores GRHBPKT antenna health data from gate readers
# ============================================================

resource "aws_dynamodb_table" "health_events" {
  name         = "${var.project_name}-health-events"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "gate_reader_id"
  range_key    = "timestamp"

  attribute {
    name = "gate_reader_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name        = "${var.project_name}-health-events"
    Environment = var.environment
  }
}