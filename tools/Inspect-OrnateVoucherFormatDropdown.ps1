<#
Read-only support probe for Ornate's Voucher Format dropdown popup list (the
Description / Voucher Name grid that appears when the Voucher Format combo
on the "Voucher Print" window is expanded). This is a SEPARATE top-level
window while open, not a child of "Voucher Print" - Inspect-
OrnateVoucherDialog.ps1 cannot see it for exactly that reason.

Run this while the dropdown is visibly open (same state as the screenshot:
Description | Voucher Name columns listing "GST Sales Voucher (A4) Shree
Aradhana" etc). Does not click, select, or close anything.
#>
[CmdletBinding()]
param()

Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;

public static class OrnateDropdownProbe {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr hWnd, EnumWindowsProc callback, IntPtr lParam);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int maxCount);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr hWnd, StringBuilder text, int maxCount);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  public static string Text(IntPtr hWnd) { var b=new StringBuilder(2048); GetWindowText(hWnd,b,b.Capacity); return b.ToString(); }
  public static string Class(IntPtr hWnd) { var b=new StringBuilder(256); GetClassName(hWnd,b,b.Capacity); return b.ToString(); }
}
'@
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$onx = @(Get-Process ONX -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
if (-not $onx) { throw 'Ornate (ONX.exe) is not running.' }

# Every visible top-level window owned by Ornate right now - the dropdown
# popup will show up here as something with no obvious title, distinct from
# the "Voucher Print" dialog itself.
$candidates = [System.Collections.Generic.List[object]]::new()
[OrnateDropdownProbe]::EnumWindows({
  param($window, $state)
  [uint32]$ownerProcessId = 0
  [OrnateDropdownProbe]::GetWindowThreadProcessId($window, [ref]$ownerProcessId) | Out-Null
  if ($onx -contains [int]$ownerProcessId -and [OrnateDropdownProbe]::IsWindowVisible($window)) {
    $candidates.Add($window)
  }
  return $true
}, [IntPtr]::Zero) | Out-Null

'Visible top-level windows owned by Ornate right now:'
foreach ($w in $candidates) {
  $rect = New-Object OrnateDropdownProbe+RECT
  [OrnateDropdownProbe]::GetWindowRect($w, [ref]$rect) | Out-Null
  [pscustomobject]@{
    Handle = $w
    Class  = [OrnateDropdownProbe]::Class($w)
    Text   = [OrnateDropdownProbe]::Text($w)
    Width  = $rect.Right - $rect.Left
    Height = $rect.Bottom - $rect.Top
  }
} | Format-Table -AutoSize

foreach ($w in $candidates) {
  $title = [OrnateDropdownProbe]::Text($w)
  if ($title -eq 'Voucher Print') { continue }

  "`n=== Probing window $w (title='$title', class='$([OrnateDropdownProbe]::Class($w))') via UI Automation ==="
  try {
    $root = [System.Windows.Automation.AutomationElement]::FromHandle($w)
    $condition = New-Object System.Windows.Automation.PropertyCondition(
      [System.Windows.Automation.AutomationElement]::IsControlElementProperty, $true)
    $elements = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition)
    $rows = foreach ($element in $elements) {
      $current = $element.Current
      $value = ''
      $pattern = $null
      if ($element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) {
        try { $value = ([System.Windows.Automation.ValuePattern]$pattern).Current.Value } catch { }
      }
      [pscustomobject]@{
        Control      = $current.ControlType.ProgrammaticName
        Name         = $current.Name
        AutomationId = $current.AutomationId
        Value        = $value
      }
    }
    $rows | Where-Object { $_.Name -or $_.Value } | Format-Table -AutoSize
  } catch {
    "  UI Automation probe failed: $($_.Exception.Message)"
  }
}
