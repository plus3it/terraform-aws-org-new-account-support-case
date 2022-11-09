module "test_create_all" {
  source = "../.."

  cc_list            = "foo@example.com"
  communication_body = "foo body"
  subject            = "foo subject"
}
