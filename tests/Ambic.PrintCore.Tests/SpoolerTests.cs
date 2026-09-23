using Ambic.PrintCore.Spooler;
using Xunit;

namespace Ambic.PrintCore.Tests;

public class SpoolerTests
{
    [Fact]
    public void PrinterDiscovery_FindsLocalPrinters()
    {
        var printers = PrinterDiscovery.DiscoverLocalPrinters();
        Assert.NotNull(printers);
        // On any real Windows machine with print spooler, at least 1 printer (e.g. PDF, XPS, or physical) exists
        Assert.NotEmpty(printers);

        foreach (var p in printers)
        {
            Assert.False(string.IsNullOrWhiteSpace(p.Name));
            Assert.NotNull(p.PortName);
        }
    }
}
