package nats

const UNKNOWN = "systemupdate.unknown"
const NOT_CONFIGURED = "systemupdate.not_configured"
const DISABLED = "systemupdate.disabled"
const NOTIFY_BEFORE_DOWNLOAD = "systemupdate.notify_before_download"
const NOTIFY_BEFORE_INSTALLATION = "systemupdate.notify_before_installation"
const NOTIFY_SCHEDULED_INSTALLATION = "systemupdate.notify_scheduled_installation"

func SystemUpdatePossibleStatus() []string {
	return []string{UNKNOWN, NOT_CONFIGURED, DISABLED, NOTIFY_BEFORE_DOWNLOAD, NOTIFY_BEFORE_INSTALLATION, NOTIFY_SCHEDULED_INSTALLATION}
}
