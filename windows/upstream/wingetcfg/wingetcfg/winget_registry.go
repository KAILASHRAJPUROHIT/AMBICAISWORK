package wingetcfg

import (
	"errors"
	"strings"
)

const (
	RegistryValueTypeString       string = "String"
	RegistryValueTypeBinary       string = "Binary"
	RegistryValueTypeDWord        string = "DWord"
	RegistryValueTypeQWord        string = "QWord"
	RegistryValueTypeMultistring  string = "MultiString"
	RegistryValueTypeExpandString string = "ExpandString"
	WinGetRegistryResource               = "xPSDesiredStateConfiguration/xRegistry"
)

// AddRegistryKey adds a registry key.
// ID is an optional identifier.
// Description is an optional text that describes the task to be performed.
// Key specifies the path to the registry key as a string. This path must include the registry hive or drive, such as HKEY_LOCAL_MACHINE or HKLM:.
// force specifies if you want to delete a registry key that has subkeys.
func AddRegistryKey(ID string, description string, key string) (*WinGetResource, error) {
	return NewWinGetRegistryResource(ID, description, key, "", "", "", EnsurePresent, false, false)
}

// AddRegistryKeyDefaultValue updates a registry key default value.
// ID is an optional identifier.
// Description is an optional text that describes the task to be performed.
// Key specifies the path to the registry key as a string. This path must include the registry hive or drive, such as HKEY_LOCAL_MACHINE or HKLM:.
// valueType specifies the type for the specified registry key value's data which is one of String, Binary, DWord, QWord, MultiString, ExpandString
// valueData specifies the registry key value as an array of string. If ValueType isn't MultiString and this property's value is multiple strings,
// force specifies if you want to delete a registry key that has subkeys.
func UpdateRegistryKeyDefaultValue(ID string, description string, key string, valueType string, valueData string, force bool) (*WinGetResource, error) {
	return NewWinGetRegistryResource(ID, description, key, "", valueType, valueData, EnsurePresent, false, force)
}

// AddRegistryValue creates a new WinGetResource that contains the settings to add a new registry value.
// Key specifies the path to the registry key as a string. This path must include the registry hive or drive, such as HKEY_LOCAL_MACHINE or HKLM:.
// valueName specifies the name of the registry value as a string.
// valueType specifies the type for the specified registry key value's data which is one of String, Binary, DWord, QWord, MultiString, ExpandString.
// valueData specifies the registry key value as an array of string. If ValueType isn't MultiString and this property's value is multiple strings,
// the function returns an invalid argument exception.
// ensure specifies whether the registry key or value should exist. To add or update a registry key or value, set this property to Present. To remove
// a registry key or value, set this property to Absent.
// hex specifies whether the specified registry key data is provided in a hexadecimal format. Specify this property only when valueType is DWord or QWord.
// If valueType isn't DWord or Qword, the resource ignores this property.
// force specifies if you want to delete a registry key that has subkeys.
func AddRegistryValue(ID string, description string, key string, valueName string, valueType string, valueData string, hex bool, force bool) (*WinGetResource, error) {
	return NewWinGetRegistryResource(ID, description, key, valueName, valueType, valueData, EnsurePresent, hex, force)
}

// RemoveRegistryKey removes a registry key.
// ID is an optional identifier.
// Description is an optional text that describes the task to be performed.
// Key specifies the path to the registry key as a string. This path must include the registry hive or drive, such as HKEY_LOCAL_MACHINE or HKLM:.
// force specifies if you want to delete a registry key that has subkeys.
func RemoveRegistryKey(ID string, description string, key string, force bool) (*WinGetResource, error) {
	return NewWinGetRegistryResource(ID, description, key, "", "", "", EnsureAbsent, false, force)
}

// RemoveRegistryValue removes a registry value from a key.
// ID is an optional identifier.
// Description is an optional text that describes the task to be performed.
// Key specifies the path to the registry key as a string. This path must include the registry hive or drive, such as HKEY_LOCAL_MACHINE or HKLM:.
// valueName specifies the name of the registry value as a string.
func RemoveRegistryValue(ID string, description string, key string, valueName string) (*WinGetResource, error) {
	return NewWinGetRegistryResource(ID, description, key, valueName, "", "", EnsureAbsent, false, false)
}

// NewWinGetRegistryResource creates a new WinGetResource that contains the settings to modify the registry.
// ID is an optional identifier.
// Description is an optional text that describes the task to be performed.
// Key specifies the path to the registry key as a string. This path must include the registry hive or drive, such as HKEY_LOCAL_MACHINE or HKLM:.
// valueName specifies the name of the registry value as a string. To add or remove a registry key, specify this property as an empty string without
// specifying the ValueType or ValueData property. To update or remove the default value of a registry key, specify this property as an empty string
// with the ValueType or ValueData property.
// valueType specifies the type for the specified registry key value's data which is one of String, Binary, DWord, QWord, MultiString, ExpandString
// valueData specifies the registry key value as an array of string. If ValueType isn't MultiString and this property's value is multiple strings,
// the function returns an invalid argument exception.
// ensure specifies whether the registry key or value should exist. To add or update a registry key or value, set this property to Present. To remove
// a registry key or value, set this property to Absent.
// hex specifies whether the specified registry key data is provided in a hexadecimal format. Specify this property only when valueType is DWord or QWord.
// If valueType isn't DWord or Qword, the resource ignores this property.
// force specifies whether to overwrite the registry key value if it already has a value or to delete a registry key that has subkeys.
// Reference: https://github.com/dsccommunity/xPSDesiredStateConfiguration/blob/main/source/DSCResources/DSC_xRegistryResource/DSC_xRegistryResource.psm1
func NewWinGetRegistryResource(ID string, description string, key string, valueName string, valueType string, valueData string, ensure string, hex bool, force bool) (*WinGetResource, error) {
	r := WinGetResource{}
	r.Resource = WinGetRegistryResource

	// ID (optional)
	if ID != "" {
		r.ID = ID
	}

	// Directives
	r.Directives.Description = description
	r.Directives.AllowPreRelease = true

	// Settings
	r.Settings = map[string]any{}

	if key == "" {
		return nil, errors.New("key cannot be empty")
	}
	r.Settings["Key"] = key

	r.Settings["ValueName"] = valueName

	if valueType != "" {
		if !IsValidRegistryValueType(valueType) {
			return nil, errors.New("value type is not valid")
		}
		r.Settings["ValueType"] = valueType
	}

	if valueData != "" {
		data := strings.Split(valueData, "\n")
		if len(data) > 1 {
			return nil, errors.New("more than one string has been passed but type is not Multitring")
		}

		r.Settings["ValueData"] = valueData
	}

	if force {
		r.Settings["Force"] = force
	}

	if valueType == RegistryValueTypeDWord || valueType == RegistryValueTypeQWord {
		r.Settings["Hex"] = hex
	}

	r.Settings["Ensure"] = SetEnsureValue(ensure)

	return &r, nil
}

func IsValidRegistryValueType(registryValueType string) bool {
	switch registryValueType {
	case "String", "Binary", "DWord", "QWord", "MultiString", "ExpandString":
		return true
	}
	return false
}
