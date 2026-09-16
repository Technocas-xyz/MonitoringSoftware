using System.Runtime.InteropServices;
using System.Runtime.Versioning;

namespace Agent.Service.Collectors;

/// <summary>
/// Global low-level keyboard/mouse hooks that ONLY increment counters. No virtual-key codes,
/// scan codes, characters, or coordinates are stored or transmitted — the callback ignores all
/// payload and just counts an event. This is what makes "aggregate activity" privacy-safe
/// (spec 23/45).
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class WindowsInputCounter : IInputCounter, IDisposable
{
    private int _keys;
    private int _mouse;
    private IntPtr _kbdHook = IntPtr.Zero;
    private IntPtr _mouseHook = IntPtr.Zero;
    private readonly LowLevelProc _kbdProc;
    private readonly LowLevelProc _mouseProc;

    private const int WH_KEYBOARD_LL = 13;
    private const int WH_MOUSE_LL = 14;

    public WindowsInputCounter()
    {
        // Keep delegates referenced so they are not GC'd while hooks are installed.
        _kbdProc = KbdCallback;
        _mouseProc = MouseCallback;
        _kbdHook = SetHook(WH_KEYBOARD_LL, _kbdProc);
        _mouseHook = SetHook(WH_MOUSE_LL, _mouseProc);
    }

    public (int keys, int mouse) SampleAndReset()
    {
        var k = Interlocked.Exchange(ref _keys, 0);
        var m = Interlocked.Exchange(ref _mouse, 0);
        return (k, m);
    }

    private IntPtr KbdCallback(int nCode, IntPtr wParam, IntPtr lParam)
    {
        // Count only. The lParam (which contains the key code) is deliberately NOT inspected.
        if (nCode >= 0) Interlocked.Increment(ref _keys);
        return CallNextHookEx(IntPtr.Zero, nCode, wParam, lParam);
    }

    private IntPtr MouseCallback(int nCode, IntPtr wParam, IntPtr lParam)
    {
        if (nCode >= 0) Interlocked.Increment(ref _mouse);
        return CallNextHookEx(IntPtr.Zero, nCode, wParam, lParam);
    }

    private static IntPtr SetHook(int idHook, LowLevelProc proc)
    {
        using var curProcess = System.Diagnostics.Process.GetCurrentProcess();
        using var curModule = curProcess.MainModule!;
        return SetWindowsHookEx(idHook, proc, GetModuleHandle(curModule.ModuleName), 0);
    }

    public void Dispose()
    {
        if (_kbdHook != IntPtr.Zero) UnhookWindowsHookEx(_kbdHook);
        if (_mouseHook != IntPtr.Zero) UnhookWindowsHookEx(_mouseHook);
        _kbdHook = _mouseHook = IntPtr.Zero;
    }

    private delegate IntPtr LowLevelProc(int nCode, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr SetWindowsHookEx(int idHook, LowLevelProc lpfn, IntPtr hMod, uint dwThreadId);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool UnhookWindowsHookEx(IntPtr hhk);
    [DllImport("user32.dll")]
    private static extern IntPtr CallNextHookEx(IntPtr hhk, int nCode, IntPtr wParam, IntPtr lParam);
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    private static extern IntPtr GetModuleHandle(string lpModuleName);
}
