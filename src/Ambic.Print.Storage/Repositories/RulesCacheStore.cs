using Ambic.PrintCore.Config;
using Ambic.PrintCore.Models;
using System.Text.Json;

namespace Ambic.Print.Storage.Repositories;

public class RulesCacheStore
{
    private readonly string _configFilePath;
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };

    public RulesCacheStore(string configFilePath)
    {
        _configFilePath = configFilePath;
        EnsureDefault();
    }

    public void EnsureDefault()
    {
        if (!File.Exists(_configFilePath))
        {
            var dir = Path.GetDirectoryName(_configFilePath);
            if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
            {
                Directory.CreateDirectory(dir);
            }
            var defaultRuleset = DefaultTopology.CreateDefaultRuleset();
            Save(defaultRuleset);
        }
    }

    public RulesetConfig Load()
    {
        try
        {
            if (File.Exists(_configFilePath))
            {
                var json = File.ReadAllText(_configFilePath);
                var config = JsonSerializer.Deserialize<RulesetConfig>(json, JsonOptions);
                if (config != null && config.Rules.Count > 0)
                {
                    return config;
                }
            }
        }
        catch
        {
            // Fall back to default
        }
        return DefaultTopology.CreateDefaultRuleset();
    }

    public void Save(RulesetConfig config)
    {
        var dir = Path.GetDirectoryName(_configFilePath);
        if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
        {
            Directory.CreateDirectory(dir);
        }
        var json = JsonSerializer.Serialize(config, JsonOptions);
        for (int i = 0; i < 3; i++)
        {
            try
            {
                using var fs = new FileStream(_configFilePath, FileMode.Create, FileAccess.Write, FileShare.ReadWrite);
                using var writer = new StreamWriter(fs, System.Text.Encoding.UTF8);
                writer.Write(json);
                break;
            }
            catch when (i < 2)
            {
                Thread.Sleep(150);
            }
        }
    }

    public RouterHubConfig LoadHubConfig()
    {
        var ruleset = Load();
        if (ruleset.HubSettings != null)
        {
            if (ruleset.HubSettings.Rules.Count == 0 && ruleset.Rules.Count > 0)
            {
                ruleset.HubSettings.Rules = ruleset.Rules;
            }
            return ruleset.HubSettings;
        }

        var defaultHub = DefaultTopology.CreateDefaultHubConfig();
        defaultHub.Rules = ruleset.Rules.Count > 0 ? ruleset.Rules : defaultHub.Rules;
        return defaultHub;
    }

    public void SaveHubConfig(RouterHubConfig hubConfig)
    {
        var ruleset = Load();
        ruleset.HubSettings = hubConfig;
        ruleset.Rules = hubConfig.Rules;
        ruleset.PublishedAtUtc = DateTime.UtcNow;
        Save(ruleset);
    }
}
