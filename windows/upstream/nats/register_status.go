package nats

const REGISTER_CERTIFICATE_SENT = "users.certificate_sent"
const REGISTER_COMPLETE = "users.completed"
const REGISTER_IN_REVIEW = "users.review_request"
const REGISTER_REVOKED = "users.certificate_revoked"
const REGISTER_APPROVED = "users.approved"
const REGISTER_PASSWORD_LINK_SENT = "users.password_link_sent"
const REGISTER_OIDC_FIRST_LOGIN = "users.oidc_first_login"
const REGISTER_SEND_CERTIFICATE = "users.send_certificate"
const REGISTER_FORCE_PASSWORD_CHANGE = "users.force_change_password"

func RegisterPossibleStatus() []string {
	return []string{REGISTER_CERTIFICATE_SENT, REGISTER_COMPLETE, REGISTER_IN_REVIEW}
}
