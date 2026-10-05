//go:build linux

package utils

func GetConfigFile() string {
	return "/etc/openuem-server/openuem.ini"
}

func GetAgentConfigFile() string {
	return "/etc/openuem-agent/openuem.ini"
}
