//go:build darwin

package utils

func GetConfigFile() string {
	return "/Library/OpenUEMServer/etc/openuem-server/openuem.ini"
}

func GetAgentConfigFile() string {
	return "/Library/OpenUEMAgent/etc/openuem-agent/openuem.ini"
}
