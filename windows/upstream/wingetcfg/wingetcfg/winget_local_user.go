package wingetcfg

import (
	"errors"
)

const (
	WinGetLocalUserResource = "xPSDesiredStateConfiguration/xUser"
)

// AddOrModifyLocalUser adds or modify a local user.
// ID is an optional identifier.
// Username is required to identify the user's account.
// Description is an optional text that describes the account.
// Disabled specifies if the account is disabled.
// Fullname is optional and specifies the full name of the account as a string
// Password specifies a credential with the password to use for this account
// PasswordChangeNotAllowed specifies whether the user can change their password,
// set this property to true to prevent the user from changing their password or
// set this property to false to allow the user to change their password.
// PasswordChangeRequired specifies whether the user must change their password,
// set this property to true to force the user to change their password the next time they sign in or
// set this property to false to not require the user to change their password.
// PasswordNeverExpires specify whether the password expires,
// set this property to true to prevent the account's password from expiring,
// set this property to $false to have the account's password expire per system security settings
func AddOrModifyLocalUser(ID, username string, description string, disabled bool, fullName, password string, passwordChangeNotAllowed, passwordChangeRequired, passwordNeverExpires bool) (*WinGetResource, error) {
	return NewLocalUserResource(ID, username, description, disabled, fullName, password, passwordChangeNotAllowed, passwordChangeRequired, passwordNeverExpires, EnsurePresent)
}

// RemoveLocalUser removes a local user.
// ID is an optional identifier.
// Username is required to identify the user's account.
func RemoveLocalUser(ID, username string) (*WinGetResource, error) {
	return NewLocalUserResource(ID, username, "", false, "", "", false, false, false, EnsureAbsent)
}

// NewLocalUserResource creates a new WinGetResource that contains the settings to manage a local user account.
// ID is an optional identifier.
// Username is required to identify the user's account.
// Description is an optional text that describes the account.
// Disabled specifies if the account is disabled.
// Fullname is optional and specifies the full name of the account as a string
// Password specifies a credential with the password to use for this account
// PasswordChangeNotAllowed specifies whether the user can change their password,
// set this property to true to prevent the user from changing their password or
// set this property to false to allow the user to change their password.
// PasswordChangeRequired specifies whether the user must change their password,
// set this property to true to force the user to change their password the next time they sign in or
// set this property to false to not require the user to change their password.
// PasswordNeverExpires specify whether the password expires,
// set this property to true to prevent the account's password from expiring,
// set this property to false to have the account's password expire per system security settings
// Reference: https://github.com/dsccommunity/xPSDesiredStateConfiguration/blob/main/source/DSCResources/DSC_xUserResource/DSC_xUserResource.psm1
func NewLocalUserResource(ID, username string, description string, disabled bool, fullName, password string, passwordChangeNotAllowed, passwordChangeRequired, passwordNeverExpires bool, ensure string) (*WinGetResource, error) {
	r := WinGetResource{}
	r.Resource = WinGetLocalUserResource

	// ID (optional)
	if ID != "" {
		r.ID = ID
	}

	// Directives
	r.Directives.Description = description
	r.Directives.AllowPreRelease = true

	// Settings
	r.Settings = map[string]any{}

	if username == "" {
		return nil, errors.New("username cannot be empty")
	}
	r.Settings["UserName"] = username
	r.Settings["Description"] = description
	r.Settings["Disabled"] = disabled
	r.Settings["FullName"] = fullName

	if password != "" {
		r.Settings["Password"] = password
	}

	r.Settings["PasswordChangeNotAllowed"] = passwordChangeNotAllowed
	r.Settings["PasswordChangeRequired"] = passwordChangeRequired
	r.Settings["PasswordNeverExpires"] = passwordNeverExpires

	r.Settings["Ensure"] = SetEnsureValue(ensure)

	return &r, nil
}
