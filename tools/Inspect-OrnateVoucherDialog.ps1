<#
Read-only support probe. Run only while Ornate's "Voucher Print" window is
visible. It does not click, focus, alter printers, or change any print job.
#>
[CmdletBinding()]
param()

Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;

public static class OrnateVoucherProbe {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr hWnd, EnumWindowsProc callback, IntPtr lParam);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int maxCount);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr hWnd, StringBuilder text, int maxCount);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [DllImport("user32.dll", SetLastError=true)] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdcBlt, uint flags);
  [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr hWnd, uint message, IntPtr wParam, IntPtr lParam);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr SendMessage(IntPtr hWnd, uint message, IntPtr wParam, StringBuilder lParam);
  public const uint CB_GETCURSEL = 0x0147;
  public const uint CB_GETLBTEXTLEN = 0x0149;
  public const uint CB_GETLBTEXT = 0x0148;
  public static string Text(IntPtr hWnd) { var b=new StringBuilder(2048); GetWindowText(hWnd,b,b.Capacity); return b.ToString(); }
  public static string Class(IntPtr hWnd) { var b=new StringBuilder(256); GetClassName(hWnd,b,b.Capacity); return b.ToString(); }
  public static string ComboSelectedText(IntPtr hWnd) {
    int index=SendMessage(hWnd,CB_GETCURSEL,IntPtr.Zero,IntPtr.Zero).ToInt32(); if(index < 0) return "";
    int length=SendMessage(hWnd,CB_GETLBTEXTLEN,(IntPtr)index,IntPtr.Zero).ToInt32(); if(length < 0) return "";
    var b=new StringBuilder(length+1); SendMessage(hWnd,CB_GETLBTEXT,(IntPtr)index,b); return b.ToString();
  }
}
'@
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing

$onx = @(Get-Process ONX -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
if (-not $onx) { throw 'Ornate (ONX.exe) is not running.' }

$dialogs = [System.Collections.Generic.List[object]]::new()
[OrnateVoucherProbe]::EnumWindows({
  param($window, $state)
  [uint32]$ownerProcessId = 0
  [OrnateVoucherProbe]::GetWindowThreadProcessId($window, [ref]$ownerProcessId) | Out-Null
  if ($onx -contains [int]$ownerProcessId -and [OrnateVoucherProbe]::IsWindowVisible($window) -and
      [OrnateVoucherProbe]::Text($window) -eq 'Voucher Print') { $dialogs.Add($window) }
  return $true
}, [IntPtr]::Zero) | Out-Null

if ($dialogs.Count -eq 0) { throw 'Open the Ornate Voucher Print window first, then run this exact command again.' }

foreach ($dialog in $dialogs) {
  "VoucherPrintHandle=$dialog"

  $rect = New-Object OrnateVoucherProbe+RECT
  if ([OrnateVoucherProbe]::GetWindowRect($dialog, [ref]$rect)) {
    $width = $rect.Right - $rect.Left
    $height = $rect.Bottom - $rect.Top
    if ($width -gt 0 -and $height -gt 0) {
      $captureRoot = 'C:\PrintBridge\routing_diagnostics'
      New-Item -ItemType Directory -Path $captureRoot -Force | Out-Null
      $capturePath = Join-Path $captureRoot ("voucher_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.png')
      $image = $null
      $graphics = $null
      try {
        $image = New-Object System.Drawing.Bitmap($width, $height)
        $graphics = [System.Drawing.Graphics]::FromImage($image)
        # PrintWindow captures the named dialog directly. CopyFromScreen is
        # wrong under RDP/DPI scaling because its coordinates are virtualized.
        $hdc = $graphics.GetHdc()
        try {
          $printed = [OrnateVoucherProbe]::PrintWindow($dialog, $hdc, 2)
        } finally {
          $graphics.ReleaseHdc($hdc)
        }
        if (-not $printed) { throw 'Windows could not capture the Voucher Print dialog.' }
        $image.Save($capturePath, [System.Drawing.Imaging.ImageFormat]::Png)
        "WindowCapture=$capturePath"

        $tesseract = 'C:\Program Files\Tesseract-OCR\tesseract.exe'
        if (Test-Path -LiteralPath $tesseract) {
          'Local OCR text:'
          & $tesseract $capturePath stdout --psm 6 2>$null
        } else {
          'Local OCR text: unavailable; Tesseract is not installed on this PC. Window capture is saved for local calibration.'
        }
      } finally {
        if ($graphics) { $graphics.Dispose() }
        if ($image) { $image.Dispose() }
      }
    }
  }

  $rows = [System.Collections.Generic.List[object]]::new()
  [OrnateVoucherProbe]::EnumChildWindows($dialog, {
    param($child, $state)
    $class = [OrnateVoucherProbe]::Class($child)
    $text = [OrnateVoucherProbe]::Text($child).Trim()
    $selected = if ($class -eq 'ComboBox') { [OrnateVoucherProbe]::ComboSelectedText($child).Trim() } else { '' }
    if ($text -or $selected -or $class -in @('ComboBox','Edit','Button','Static')) {
      $rows.Add([pscustomobject]@{ Class=$class; Text=$text; Selected=$selected })
    }
    return $true
  }, [IntPtr]::Zero) | Out-Null
  $rows | Format-Table -AutoSize

  # Ornate renders the Voucher Format selector as a custom Windows Forms
  # control. Its value is often absent from Win32 window text, but exposed
  # through UI Automation. This remains strictly read-only.
  'UI Automation fields:'
  $root = [System.Windows.Automation.AutomationElement]::FromHandle($dialog)
  $condition = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::IsControlElementProperty, $true)
  $elements = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition)
  $uiaRows = foreach ($element in $elements) {
    $current = $element.Current
    $value = ''
    $pattern = $null
    if ($element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) {
      try { $value = ([System.Windows.Automation.ValuePattern]$pattern).Current.Value } catch { }
    }
    [pscustomobject]@{
      Control = $current.ControlType.ProgrammaticName
      Name = $current.Name
      AutomationId = $current.AutomationId
      Value = $value
    }
  }
  $uiaRows | Where-Object { $_.Name -or $_.AutomationId -or $_.Value } | Format-Table -AutoSize
}
