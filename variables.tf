variable "cc_list" {
  description = "Comma-separated list of email addresses to CC on this case.  At least one email address is required."
  type        = string
}

variable "communication_body" {
  description = "Text for body of the communication sent to support.  The variable 'account_id' can be used within the text if preceded by a dollar sign and optionally enclosed by curly braces."
  type        = string
}

variable "lambda" {
  description = "Map of any additional arguments for the upstream lambda module. See <https://github.com/terraform-aws-modules/terraform-aws-lambda>"
  type        = any
  default     = {}
}

variable "log_level" {
  default     = "info"
  description = "Log level of the lambda output, one of: debug, info, warning, error, critical"
  type        = string
}

variable "subject" {
  description = "Text for 'Subject' field of the communication sent to support.  The variable 'account_id' can be used within the text if preceded by a dollar sign and optionally enclosed by curly braces."
  type        = string
}

variable "tags" {
  default     = {}
  description = "Tags that are passed to resources"
  type        = map(string)
}
