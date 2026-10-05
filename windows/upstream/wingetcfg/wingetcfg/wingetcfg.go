package wingetcfg

import (
	"os"

	"gopkg.in/yaml.v3"
)

const DSCSchema = "# yaml-language-server: $schema=https://aka.ms/configuration-dsc-schema/0.2"
const WinGetConfigurationVersion = "0.2.0"

const (
	EnsurePresent string = "Present"
	EnsureAbsent  string = "Absent"
)

type WinGetDirectives struct {
	Description     string `yaml:"description"`
	AllowPreRelease bool   `yaml:"allowPrerelease"`
}

type WinGetResource struct {
	Resource   string `yaml:"resource"`
	ID         string `yaml:"id,omitempty"`
	DependsOn  string `yaml:"dependsOn,omitempty"`
	Directives WinGetDirectives
	Settings   map[string]any
}

type WinGetProperties struct {
	Assertions           []*WinGetResource `yaml:"assertions,omitempty"`
	Resources            []*WinGetResource `yaml:"resources,omitempty"`
	ConfigurationVersion string            `yaml:"configurationVersion"`
}

type WinGetCfg struct {
	Properties WinGetProperties `yaml:"properties"`
}

func NewWingetCfg() *WinGetCfg {
	cfg := WinGetCfg{}
	cfg.Properties.ConfigurationVersion = WinGetConfigurationVersion
	return &cfg
}

func (cfg *WinGetCfg) AddResource(resource *WinGetResource) {
	cfg.Properties.Resources = append(cfg.Properties.Resources, resource)
}

func (cfg *WinGetCfg) AddAssertion(resource *WinGetResource) {
	cfg.Properties.Assertions = append(cfg.Properties.Assertions, resource)
}

func (cfg *WinGetCfg) WriteConfigFile(filePath string) error {
	f, err := os.Create(filePath)
	if err != nil {
		return err
	}
	defer f.Close()

	// Add schema header
	if _, err = f.WriteString(DSCSchema + "\n"); err != nil {
		return err
	}

	out, err := yaml.Marshal(cfg)
	if err != nil {
		return err
	}

	if _, err := f.Write(out); err != nil {
		return err
	}

	if err := f.Sync(); err != nil {
		return err
	}

	return nil
}

func SetEnsureValue(ensure string) string {
	switch ensure {
	case EnsurePresent, EnsureAbsent:
		return ensure
	}
	return EnsurePresent
}
