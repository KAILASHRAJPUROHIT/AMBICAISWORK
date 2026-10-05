package nats

type WingetPackage struct {
	ID   string `json:"ID,omitempty"`
	Name string `json:"name,omitempty"`
}

type SoftwarePackage struct {
	ID     string `json:"ID,omitempty"`
	Name   string `json:"name,omitempty"`
	Source string `json:"source,omitempty"`
}

// WingetCfgDeploy allows the agent to inform if a package
// has been installed or desinstalled using Winget configure
type WingetCfgDeploy struct {
	PackageID string `json:"PackageID,omitempty"`
	Installed bool   `json:"installed,omitempty"`
}
