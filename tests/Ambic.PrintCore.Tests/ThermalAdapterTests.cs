using Ambic.PrintAdapters.Thermal;

namespace Ambic.PrintCore.Tests;

public class ThermalAdapterTests
{
    [Fact]
    public void FormatTestTicket_GeneratesValidEscPosBytes()
    {
        var formatter = new ThermalReceiptFormatter(48);
        var bytes = formatter.FormatTestTicket("GOLD01", "Thermal Printer");

        Assert.NotNull(bytes);
        Assert.True(bytes.Length > 20);

        // Begins with ESC @ (0x1B, 0x40)
        Assert.Equal(0x1B, bytes[0]);
        Assert.Equal(0x40, bytes[1]);

        // Ends with paper cut (0x1D, 0x56, 0x42, 0x00)
        Assert.Equal(0x1D, bytes[^4]);
        Assert.Equal(0x56, bytes[^3]);
        Assert.Equal(0x42, bytes[^2]);
        Assert.Equal(0x00, bytes[^1]);
    }

    [Fact]
    public void FormatEstimate_IncludesTotalsAndItems()
    {
        var formatter = new ThermalReceiptFormatter(48);
        var receipt = new EstimateReceipt
        {
            EstimateNumber = "EST-9901",
            CustomerName = "Arun",
            GrandTotal = 54000.00m,
            Items =
            [
                new EstimateItem
                {
                    Description = "Gold Chain",
                    Purity = "22K",
                    NetWeightGrams = 8.5m,
                    RatePerGram = 6800m,
                    TotalAmount = 57800m
                }
            ]
        };

        var bytes = formatter.FormatEstimate(receipt);
        Assert.NotNull(bytes);
        Assert.True(bytes.Length > 100);

        var text = System.Text.Encoding.GetEncoding(1252).GetString(bytes);
        Assert.Contains("EST-9901", text);
        Assert.Contains("ESTIMATE VOUCHER", text);
        Assert.Contains("Gold Chain", text);
        Assert.Contains("TOTAL", text);
    }
}
