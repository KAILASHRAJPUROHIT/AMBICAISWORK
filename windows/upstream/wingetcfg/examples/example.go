package main

import (
	"log"
	"os"
	"path/filepath"

	"github.com/open-uem/wingetcfg/wingetcfg"
)

func main() {
	path, err := os.Getwd()
	if err != nil {
		log.Fatalf("could not get working directory")
	}

	cfg1 := wingetcfg.NewWingetCfg()

	uninstallPackage, err := wingetcfg.UninstallPackage("", "uninstall google chrome", "Google.Chrome", "", "", true)
	if err != nil {
		log.Fatalf("could not create package resource: %v", err)
	}

	cfg1.AddResource(uninstallPackage)

	if err := cfg1.WriteConfigFile(filepath.Join(path, "uninstall_package.winget")); err != nil {
		log.Printf("error found: %v\n", err)
	}

	cfg2 := wingetcfg.NewWingetCfg()

	installPackage, err := wingetcfg.InstallPackage("", "install google chrome", "Google.Chrome", "", "", true)
	if err != nil {
		log.Fatalf("could not create package resource: %v", err)
	}

	cfg2.AddResource(installPackage)

	if err := cfg2.WriteConfigFile(filepath.Join(path, "install_package.winget")); err != nil {
		log.Printf("error found: %v\n", err)
	}

	cfg3 := wingetcfg.NewWingetCfg()

	editRegistry, err := wingetcfg.AddRegistryValue("", "add registry value to existing value", `HKEY_USERS\.DEFAULT\Control Panel\Keyboard`, "InitialKeyboardIndicators", wingetcfg.RegistryValueTypeString, "2147483650", false, true)
	if err != nil {
		log.Fatalf("could not create package resource: %v", err)
	}

	cfg3.AddResource(editRegistry)

	if err := cfg3.WriteConfigFile(filepath.Join(path, "add_registry_value.winget")); err != nil {
		log.Printf("error found: %v\n", err)
	}
}
