package wingetcfg

import "errors"

const (
	FileHashMD5              string = "MD5"
	FileHashRIPEMD160        string = "RIPEMD160"
	FileHashSHA1             string = "SHA1"
	FileHashSHA256           string = "SHA256"
	FileHashSHA384           string = "SHA384"
	FileHashSHA512           string = "SHA512"
	WinGetMSIPackageResource        = "xPSDesiredStateConfiguration/xMsiPackage"
)

func InstallMSIPackage(ID string, description string, productID string, path string, arguments string, logPath string, fileHash string, hashAlgorithm string) (*WinGetResource, error) {
	return NewMSIPackageResource(ID, description, productID, path, arguments, logPath, fileHash, hashAlgorithm, true)
}

func UninstallMSIPackage(ID string, description string, productID string, path string, arguments string, logPath string, fileHash string, hashAlgorithm string) (*WinGetResource, error) {
	return NewMSIPackageResource(ID, description, productID, path, arguments, logPath, fileHash, hashAlgorithm, false)
}

// NewMSIPackageResource creates a new WinGetResource that contains the settings to manage a local user account.
// ID is an optional identifier.
// Description is an optional text that describes the task to be performed.
// ProductID is required to find the package, usually a GUID
// Path is required and the path to the MSI file to install or uninstall
// Arguments to pass to the MSI package during installation or uninstallation (optional)
// LogPath. The path to the log file to log the output from the MSI execution
// FileHash. The expected hash value of the MSI file at the given path (optional).
// HashAlgorithm. The algorithm used to generate the given hash value.
// Ensure specifies whether the MSI file should be installed or uninstalled. Set this property to
// Present to install the MSI, and Absent to uninstall the MSI
// Reference: https://github.com/dsccommunity/xPSDesiredStateConfiguration/blob/main/source/DSCResources/DSC_xMsiPackage/DSC_xMsiPackage.psm1
func NewMSIPackageResource(ID string, description string, productID string, path string, arguments string, logPath string, fileHash string, hashAlgorithm string, ensure bool) (*WinGetResource, error) {
	r := WinGetResource{}
	r.Resource = WinGetMSIPackageResource

	// ID (optional)
	if ID != "" {
		r.ID = ID
	}

	// Directives
	r.Directives.Description = description
	r.Directives.AllowPreRelease = true

	// Settings
	r.Settings = map[string]any{}

	// if productID == "" {
	// 	return nil, errors.New("productID cannot be empty")
	// }
	// r.Settings["ProductId"] = productID

	if path == "" {
		return nil, errors.New("path cannot be empty")
	}
	r.Settings["Path"] = path

	if arguments != "" {
		r.Settings["Arguments"] = arguments
	}

	// if hashAlgorithm != "" && fileHash != "" {
	// 	r.Settings["FileHash"] = fileHash
	// 	r.Settings["HashAlgorithm"] = hashAlgorithm
	// }

	if logPath != "" {
		r.Settings["LogPath"] = logPath
	}

	if ensure {
		r.Settings["Ensure"] = "Present"
	} else {
		r.Settings["Ensure"] = "Absent"
	}

	return &r, nil
}
