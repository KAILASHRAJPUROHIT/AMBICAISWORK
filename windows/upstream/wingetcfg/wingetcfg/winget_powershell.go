package wingetcfg

const (
	OpenUEMPowershell = "openuem/Powershell"
)

// As there's no specific Powershell DSC that runs powershell scripts we create a custom resource
func ExecutePowershellScript(id string, name string, pwshell string, run string) (*WinGetResource, error) {
	r := WinGetResource{}
	r.Resource = OpenUEMPowershell

	// Settings
	r.Settings = map[string]any{}
	r.Settings["ID"] = id
	r.Settings["Script"] = pwshell
	r.Settings["ScriptRun"] = run
	r.Settings["Name"] = name

	return &r, nil
}
