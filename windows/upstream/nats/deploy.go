package nats

import "time"

type DeployAction struct {
	AgentId         string    `json:"agentid,omitempty"`
	Action          string    `json:"action,omitempty"`
	When            time.Time `json:"when,omitempty"`
	PackageId       string    `json:"packageid,omitempty"`
	PackageName     string    `json:"packagename,omitempty"`
	PackageVersion  string    `json:"packageversion,omitempty"`
	PackageBranch   string    `json:"packagebranch,omitempty"`
	PackageBrewType string    `json:"packagebrewtype,omitempty"`
	PackageVerified bool      `json:"packageverified,omitempty"`
	Repository      string    `json:"repository,omitempty"`
	Info            string    `json:"info,omitempty"`
	Failed          bool      `json:"failed,omitempty"`
}
