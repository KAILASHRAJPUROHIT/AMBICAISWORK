package nats

import (
	ansiblecfg "github.com/open-uem/openuem-ansible-config/ansible"
	"github.com/open-uem/wingetcfg/wingetcfg"
)

type CfgProfiles struct {
	AgentID   string `json:"agentID,omitempty"`
	ProfileID int    `json:"profileID,omitempty"`
}

type ProfileConfig struct {
	ProfileID     int                           `yaml:"profileID"`
	Exclusions    []string                      `yaml:"exclusions"`
	Deployments   []string                      `yaml:"deployments"`
	WinGetConfig  *wingetcfg.WinGetCfg          `yaml:"config,omitempty"`
	AnsibleConfig []*ansiblecfg.AnsiblePlaybook `yaml:"ansible,omitempty"`
	NetBirdConfig []*NetbirdTask                `yaml:"netbird,omitempty"`
}

type TaskReport struct {
	Name    string `json:"name"`
	Failed  bool   `json:"failed"`
	EndTime string `json:"end_time"`
	StdOut  string `json:"std_out"`
	StdErr  string `json:"std_err"`
}

type ProfileReport struct {
	ProfileID int          `json:"profileID,omitempty"`
	AgentID   string       `json:"agentID,omitempty"`
	Success   bool         `json:"success,omitempty"`
	Error     string       `json:"error,omitempty"`
	Tasks     []TaskReport `json:"tasks"`
}
