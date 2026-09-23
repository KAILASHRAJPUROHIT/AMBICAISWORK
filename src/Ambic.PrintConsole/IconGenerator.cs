using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;

namespace Ambic.PrintConsole;

public static class IconGenerator
{
    public static void Generate(string outputPath)
    {
        int[] sizes = [256, 48, 32, 16];
        var pngBytesList = new List<byte[]>();

        foreach (int size in sizes)
        {
            using var bmp = new Bitmap(size, size, PixelFormat.Format32bppArgb);
            using (var g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.InterpolationMode = InterpolationMode.HighQualityBicubic;
                g.PixelOffsetMode = PixelOffsetMode.HighQuality;

                float scale = size / 256f;

                // Background rounded badge (Dark Enterprise Slate #121826)
                float pad = 12f * scale;
                float badgeSize = size - (2 * pad);
                float cornerRadius = 48f * scale;

                using (var path = GetRoundedRect(pad, pad, badgeSize, badgeSize, cornerRadius))
                {
                    using (var brush = new LinearGradientBrush(new PointF(0, pad), new PointF(0, pad + badgeSize),
                        Color.FromArgb(28, 38, 58), Color.FromArgb(14, 18, 28)))
                    {
                        g.FillPath(brush, path);
                    }
                    using (var pen = new Pen(Color.FromArgb(50, 70, 100), 2.5f * scale))
                    {
                        g.DrawPath(pen, path);
                    }
                }

                // Top paper sheet
                float paperX = 72f * scale;
                float paperY = 30f * scale;
                float paperW = 112f * scale;
                float paperH = 75f * scale;
                using (var paperBrush = new SolidBrush(Color.FromArgb(245, 248, 252)))
                {
                    g.FillRectangle(paperBrush, paperX, paperY, paperW, paperH);
                }
                // Document lines
                using (var linePen = new Pen(Color.FromArgb(175, 190, 210), 3.5f * scale))
                {
                    g.DrawLine(linePen, paperX + 16f * scale, paperY + 20f * scale, paperX + paperW - 16f * scale, paperY + 20f * scale);
                    g.DrawLine(linePen, paperX + 16f * scale, paperY + 36f * scale, paperX + paperW - 16f * scale, paperY + 36f * scale);
                    g.DrawLine(linePen, paperX + 16f * scale, paperY + 52f * scale, paperX + paperW - 36f * scale, paperY + 52f * scale);
                }

                // Printer main body
                float bodyX = 36f * scale;
                float bodyY = 92f * scale;
                float bodyW = 184f * scale;
                float bodyH = 96f * scale;
                float bodyCorner = 18f * scale;
                using (var bodyPath = GetRoundedRect(bodyX, bodyY, bodyW, bodyH, bodyCorner))
                {
                    using (var bodyBrush = new LinearGradientBrush(new PointF(0, bodyY), new PointF(0, bodyY + bodyH),
                        Color.FromArgb(240, 244, 250), Color.FromArgb(200, 210, 225)))
                    {
                        g.FillPath(bodyBrush, bodyPath);
                    }
                    using (var bodyPen = new Pen(Color.FromArgb(150, 170, 195), 1.5f * scale))
                    {
                        g.DrawPath(bodyPen, bodyPath);
                    }
                }

                // Output slot
                float slotX = 56f * scale;
                float slotY = 132f * scale;
                float slotW = 144f * scale;
                float slotH = 22f * scale;
                using (var slotPath = GetRoundedRect(slotX, slotY, slotW, slotH, 6f * scale))
                {
                    using var slotBrush = new SolidBrush(Color.FromArgb(28, 38, 54));
                    g.FillPath(slotBrush, slotPath);
                }

                // Output paper
                float outPaperX = 72f * scale;
                float outPaperY = 140f * scale;
                float outPaperW = 112f * scale;
                float outPaperH = 58f * scale;
                using (var outPath = GetRoundedRect(outPaperX, outPaperY, outPaperW, outPaperH, 8f * scale))
                {
                    using (var outBrush = new SolidBrush(Color.White))
                    {
                        g.FillPath(outBrush, outPath);
                    }
                    using (var outPen = new Pen(Color.FromArgb(195, 210, 228), 1.5f * scale))
                    {
                        g.DrawPath(outPen, outPath);
                    }
                    // Accent header on printed document
                    using var blueBrush = new SolidBrush(Color.FromArgb(24, 115, 225));
                    g.FillRectangle(blueBrush, outPaperX + 16f * scale, outPaperY + 16f * scale, outPaperW - 32f * scale, 7f * scale);
                }

                // Status LED (Pulse Emerald Green)
                float ledX = 188f * scale;
                float ledY = 108f * scale;
                float ledR = 15f * scale;
                using (var glowBrush = new SolidBrush(Color.FromArgb(90, 34, 197, 94)))
                {
                    g.FillEllipse(glowBrush, ledX - 3f * scale, ledY - 3f * scale, (ledR + 6f) * scale, (ledR + 6f) * scale);
                }
                using (var ledBrush = new SolidBrush(Color.FromArgb(34, 197, 94)))
                {
                    g.FillEllipse(ledBrush, ledX, ledY, ledR * scale, ledR * scale);
                }
            }

            using var ms = new MemoryStream();
            bmp.Save(ms, ImageFormat.Png);
            pngBytesList.Add(ms.ToArray());
        }

        // Write multi-image ICO container
        using var fs = new FileStream(outputPath, FileMode.Create, FileAccess.Write);
        using var bw = new BinaryWriter(fs);

        // ICONDIR
        bw.Write((ushort)0); // Reserved
        bw.Write((ushort)1); // Type: 1 = ICO
        bw.Write((ushort)sizes.Length); // Image count

        int offset = 6 + (16 * sizes.Length);

        for (int i = 0; i < sizes.Length; i++)
        {
            int s = sizes[i];
            byte[] data = pngBytesList[i];

            bw.Write((byte)(s >= 256 ? 0 : s)); // Width
            bw.Write((byte)(s >= 256 ? 0 : s)); // Height
            bw.Write((byte)0); // Color palette count
            bw.Write((byte)0); // Reserved
            bw.Write((ushort)1); // Color planes
            bw.Write((ushort)32); // Bits per pixel
            bw.Write((uint)data.Length); // Image size in bytes
            bw.Write((uint)offset); // Offset of image data

            offset += data.Length;
        }

        // Image data
        for (int i = 0; i < sizes.Length; i++)
        {
            bw.Write(pngBytesList[i]);
        }
    }

    private static GraphicsPath GetRoundedRect(float x, float y, float width, float height, float radius)
    {
        var path = new GraphicsPath();
        float diameter = radius * 2f;
        path.AddArc(x, y, diameter, diameter, 180, 90);
        path.AddArc(x + width - diameter, y, diameter, diameter, 270, 90);
        path.AddArc(x + width - diameter, y + height - diameter, diameter, diameter, 0, 90);
        path.AddArc(x, y + height - diameter, diameter, diameter, 90, 90);
        path.CloseFigure();
        return path;
    }
}
