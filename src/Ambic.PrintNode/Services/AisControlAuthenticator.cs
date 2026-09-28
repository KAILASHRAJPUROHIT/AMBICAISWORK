using System.Security.Cryptography;
using System.Text;

namespace Ambic.PrintNode.Services;

/// <summary>
/// Guard for the AIS control-plane surface. This is intentionally separate from
/// job ingress: an unconfigured node must never accidentally expose remote
/// administration simply because it has started listening on a LAN port.
/// </summary>
public sealed class AisControlAuthenticator
{
    private readonly IConfiguration _configuration;

    public AisControlAuthenticator(IConfiguration configuration) => _configuration = configuration;

    public bool IsAuthorized(HttpRequest request)
    {
        var configuredToken = _configuration["AisControl:SharedToken"];
        if (string.IsNullOrWhiteSpace(configuredToken)) return false;

        var supplied = request.Headers.Authorization.ToString();
        const string prefix = "Bearer ";
        if (!supplied.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) return false;

        var suppliedBytes = Encoding.UTF8.GetBytes(supplied[prefix.Length..]);
        var expectedBytes = Encoding.UTF8.GetBytes(configuredToken);
        return suppliedBytes.Length == expectedBytes.Length &&
               CryptographicOperations.FixedTimeEquals(suppliedBytes, expectedBytes);
    }

    public bool WritesEnabled => _configuration.GetValue("AisControl:EnableRoutingWrites", false);
}
