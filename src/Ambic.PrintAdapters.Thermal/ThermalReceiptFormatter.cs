using System.Text;

namespace Ambic.PrintAdapters.Thermal;

public class EstimateItem
{
    public string Description { get; set; } = string.Empty;
    public string? Purity { get; set; }
    public decimal GrossWeightGrams { get; set; }
    public decimal NetWeightGrams { get; set; }
    public decimal RatePerGram { get; set; }
    public decimal MakingCharges { get; set; }
    public decimal TotalAmount { get; set; }
}

public class EstimateReceipt
{
    public string EstimateNumber { get; set; } = string.Empty;
    public DateTime Timestamp { get; set; } = DateTime.Now;
    public string? CustomerName { get; set; }
    public string? CustomerPhone { get; set; }
    public string? SalesPerson { get; set; }
    public List<EstimateItem> Items { get; set; } = [];
    public decimal Subtotal { get; set; }
    public decimal GstAmount { get; set; }
    public decimal GrandTotal { get; set; }
    public string? Disclaimer { get; set; }
}

public static class EscPosCommands
{
    public static readonly byte[] Initialize = [0x1B, 0x40];
    public static readonly byte[] AlignLeft = [0x1B, 0x61, 0x00];
    public static readonly byte[] AlignCenter = [0x1B, 0x61, 0x01];
    public static readonly byte[] AlignRight = [0x1B, 0x61, 0x02];
    public static readonly byte[] BoldOn = [0x1B, 0x45, 0x01];
    public static readonly byte[] BoldOff = [0x1B, 0x45, 0x00];
    public static readonly byte[] DoubleSize = [0x1D, 0x21, 0x11];
    public static readonly byte[] DoubleHeight = [0x1D, 0x21, 0x01];
    public static readonly byte[] NormalSize = [0x1D, 0x21, 0x00];
    public static readonly byte[] CutPaper = [0x1D, 0x56, 0x42, 0x00];
}

public class ThermalReceiptFormatter
{
    private readonly int _charWidth;
    private readonly Encoding _encoding;

    public ThermalReceiptFormatter(int charWidth = 48)
    {
        _charWidth = charWidth;
        Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);
        _encoding = Encoding.GetEncoding(1252);
    }

    public byte[] FormatRawText(string text, bool cut = true)
    {
        using var ms = new MemoryStream();
        ms.Write(EscPosCommands.Initialize);
        ms.Write(EscPosCommands.AlignLeft);
        ms.Write(EscPosCommands.NormalSize);

        var bytes = _encoding.GetBytes(text);
        ms.Write(bytes);
        ms.Write([0x0A, 0x0A, 0x0A, 0x0A]);

        if (cut)
        {
            ms.Write(EscPosCommands.CutPaper);
        }

        return ms.ToArray();
    }

    public byte[] FormatTestTicket(string nodeName, string printerName)
    {
        using var ms = new MemoryStream();
        ms.Write(EscPosCommands.Initialize);
        ms.Write(EscPosCommands.AlignCenter);
        ms.Write(EscPosCommands.DoubleSize);
        ms.Write(EscPosCommands.BoldOn);
        WriteString(ms, "PRINT SERVER\n");
        ms.Write(EscPosCommands.NormalSize);
        ms.Write(EscPosCommands.BoldOff);
        WriteString(ms, "AMBIC PRINT SERVER - TEST PRINT\n");
        WriteString(ms, new string('-', _charWidth) + "\n");
        ms.Write(EscPosCommands.AlignLeft);
        WriteString(ms, $"Node:    {nodeName}\n");
        WriteString(ms, $"Printer: {printerName}\n");
        WriteString(ms, $"Time:    {DateTime.Now:yyyy-MM-dd HH:mm:ss}\n");
        WriteString(ms, $"Status:  ONLINE / VERIFIED\n");
        WriteString(ms, new string('-', _charWidth) + "\n");
        ms.Write(EscPosCommands.AlignCenter);
        WriteString(ms, "Thermal Subsystem Functional\n\n\n\n");
        ms.Write(EscPosCommands.CutPaper);

        return ms.ToArray();
    }

    public byte[] FormatEstimate(EstimateReceipt receipt)
    {
        using var ms = new MemoryStream();
        ms.Write(EscPosCommands.Initialize);

        // Header
        ms.Write(EscPosCommands.AlignCenter);
        ms.Write(EscPosCommands.DoubleSize);
        ms.Write(EscPosCommands.BoldOn);
        WriteString(ms, "ESTIMATE VOUCHER\n");
        ms.Write(EscPosCommands.NormalSize);
        ms.Write(EscPosCommands.BoldOff);
        WriteString(ms, "Showroom & Retail\n");
        WriteString(ms, new string('=', _charWidth) + "\n");

        // Meta info
        ms.Write(EscPosCommands.AlignLeft);
        WriteString(ms, FormatTwoColumns($"Est #: {receipt.EstimateNumber}", receipt.Timestamp.ToString("dd-MMM-yyyy HH:mm")) + "\n");
        if (!string.IsNullOrEmpty(receipt.CustomerName))
        {
            WriteString(ms, $"Cust: {receipt.CustomerName}\n");
        }
        if (!string.IsNullOrEmpty(receipt.CustomerPhone))
        {
            WriteString(ms, $"Phone: {receipt.CustomerPhone}\n");
        }
        if (!string.IsNullOrEmpty(receipt.SalesPerson))
        {
            WriteString(ms, $"Sales: {receipt.SalesPerson}\n");
        }
        WriteString(ms, new string('-', _charWidth) + "\n");

        // Table Header
        WriteString(ms, FormatRow("ITEM / PURITY", "WEIGHT", "RATE", "AMOUNT") + "\n");
        WriteString(ms, new string('-', _charWidth) + "\n");

        // Items
        foreach (var item in receipt.Items)
        {
            string desc = item.Description;
            if (!string.IsNullOrEmpty(item.Purity))
                desc += $" ({item.Purity})";

            WriteString(ms, $"{desc}\n");

            string wtStr = $"{item.NetWeightGrams:F3}g";
            string rateStr = $"@{item.RatePerGram:N0}";
            string amtStr = $"{item.TotalAmount:N2}";

            WriteString(ms, FormatRow("", wtStr, rateStr, amtStr) + "\n");
            if (item.MakingCharges > 0)
            {
                WriteString(ms, $"  Making: Rs. {item.MakingCharges:N2}\n");
            }
        }

        WriteString(ms, new string('-', _charWidth) + "\n");

        // Totals
        ms.Write(EscPosCommands.AlignRight);
        WriteString(ms, $"Subtotal: Rs. {receipt.Subtotal:N2}\n");
        if (receipt.GstAmount > 0)
        {
            WriteString(ms, $"GST (3%): Rs. {receipt.GstAmount:N2}\n");
        }

        ms.Write(EscPosCommands.DoubleHeight);
        ms.Write(EscPosCommands.BoldOn);
        WriteString(ms, $"TOTAL: Rs. {receipt.GrandTotal:N2}\n");
        ms.Write(EscPosCommands.NormalSize);
        ms.Write(EscPosCommands.BoldOff);

        WriteString(ms, new string('=', _charWidth) + "\n");

        // Disclaimer
        ms.Write(EscPosCommands.AlignCenter);
        string disclaimer = receipt.Disclaimer ?? "* Estimate valid for date of issue only *\n* Gold rates subject to daily market change *";
        WriteString(ms, $"{disclaimer}\n");
        WriteString(ms, "Thank You For Visiting\n\n\n\n");

        ms.Write(EscPosCommands.CutPaper);

        return ms.ToArray();
    }

    private void WriteString(MemoryStream ms, string text)
    {
        var bytes = _encoding.GetBytes(text);
        ms.Write(bytes, 0, bytes.Length);
    }

    private string FormatTwoColumns(string left, string right)
    {
        int spaces = _charWidth - left.Length - right.Length;
        if (spaces < 1) spaces = 1;
        return left + new string(' ', spaces) + right;
    }

    private string FormatRow(string col1, string col2, string col3, string col4)
    {
        // For 48 char thermal printer:
        // Col1 (Description): 18 chars
        // Col2 (Weight): 9 chars
        // Col3 (Rate): 9 chars
        // Col4 (Amount): 12 chars
        int w1 = 18;
        int w2 = 9;
        int w3 = 9;
        int w4 = _charWidth - w1 - w2 - w3;

        string c1 = col1.PadRight(w1);
        if (c1.Length > w1) c1 = c1.Substring(0, w1);

        string c2 = col2.PadLeft(w2);
        string c3 = col3.PadLeft(w3);
        string c4 = col4.PadLeft(w4);

        return c1 + c2 + c3 + c4;
    }
}
