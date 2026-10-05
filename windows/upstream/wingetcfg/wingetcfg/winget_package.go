package wingetcfg

import "errors"

const WinGetPackageResource = "Microsoft.WinGet.DSC/WinGetPackage"

func InstallPackage(ID string, description string, packageID string, source string, version string, useLatest bool) (*WinGetResource, error) {
	return NewWinGetPackageResource(ID, description, packageID, source, version, useLatest, true)
}

func UninstallPackage(ID string, description string, packageID string, source string, version string, useLatest bool) (*WinGetResource, error) {
	return NewWinGetPackageResource(ID, description, packageID, source, version, useLatest, false)
}

// Reference: https://github.com/microsoft/winget-cli/blob/master/src/PowerShell/Microsoft.WinGet.DSC/Microsoft.WinGet.DSC.psm1
func NewWinGetPackageResource(ID string, description string, packageID string, source string, version string, useLatest bool, ensure bool) (*WinGetResource, error) {
	r := WinGetResource{}
	r.Resource = WinGetPackageResource

	// ID (optional)
	if ID != "" {
		r.ID = ID
	}

	// Directives
	r.Directives.Description = description
	r.Directives.AllowPreRelease = true

	// Settings
	r.Settings = map[string]any{}

	if packageID == "" {
		return nil, errors.New("packageID cannot be empty")
	}
	r.Settings["id"] = packageID

	if source != "" {
		r.Settings["source"] = source
	} else {
		r.Settings["source"] = "winget"
	}

	r.Settings["uselatest"] = useLatest

	if version != "" && !useLatest {
		r.Settings["version"] = version
		r.Settings["uselatest"] = false
	}

	if ensure {
		r.Settings["Ensure"] = "Present"
	} else {
		r.Settings["Ensure"] = "Absent"
	}

	return &r, nil
}
