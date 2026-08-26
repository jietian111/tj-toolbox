using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using Microsoft.Win32;
using System.Windows.Forms;

[StructLayout(LayoutKind.Sequential)]
public struct ShellPoint
{
    public int X;
    public int Y;
}

[ComImport, Guid("6D5140C1-7436-11CE-8034-00AA006009FA"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface INativeServiceProvider
{
    [PreserveSig]
    int QueryService(ref Guid service, ref Guid riid, out IntPtr result);
}

[ComImport, Guid("000214E2-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface INativeShellBrowser
{
    [PreserveSig] int GetWindow(out IntPtr window);
    [PreserveSig] int ContextSensitiveHelp([MarshalAs(UnmanagedType.Bool)] bool enterMode);
    [PreserveSig] int InsertMenusSB(IntPtr sharedMenu, IntPtr menuWidths);
    [PreserveSig] int SetMenuSB(IntPtr sharedMenu, IntPtr holeMenu, IntPtr activeObject);
    [PreserveSig] int RemoveMenusSB(IntPtr sharedMenu);
    [PreserveSig] int SetStatusTextSB([MarshalAs(UnmanagedType.LPWStr)] string statusText);
    [PreserveSig] int EnableModelessSB([MarshalAs(UnmanagedType.Bool)] bool enable);
    [PreserveSig] int TranslateAcceleratorSB(IntPtr message, ushort commandId);
    [PreserveSig] int BrowseObject(IntPtr pidl, uint flags);
    [PreserveSig] int GetViewStateStream(uint mode, out IntPtr stream);
    [PreserveSig] int GetControlWindow(uint controlId, out IntPtr window);
    [PreserveSig] int SendControlMsg(uint controlId, uint message, IntPtr wParam, IntPtr lParam, out IntPtr result);
    [PreserveSig] int QueryActiveShellView(out IntPtr shellView);
    [PreserveSig] int OnViewWindowActive(IntPtr shellView);
    [PreserveSig] int SetToolbarItems(IntPtr buttons, uint count, uint flags);
}

[ComImport, Guid("CDE725B0-CCC9-4519-917E-325D72FAB4CE"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface INativeFolderView
{
    [PreserveSig] int GetCurrentViewMode(out uint viewMode);
    [PreserveSig] int SetCurrentViewMode(uint viewMode);
    [PreserveSig] int GetFolder(ref Guid riid, out IntPtr folder);
    [PreserveSig] int Item(int index, out IntPtr pidl);
    [PreserveSig] int ItemCount(uint flags, out int count);
    [PreserveSig] int Items(uint flags, ref Guid riid, out IntPtr items);
    [PreserveSig] int GetSelectionMarkedItem(out int index);
    [PreserveSig] int GetFocusedItem(out int index);
    [PreserveSig] int GetItemPosition(IntPtr pidl, out ShellPoint point);
    [PreserveSig] int GetSpacing(ref ShellPoint point);
    [PreserveSig] int GetDefaultSpacing(out ShellPoint point);
    [PreserveSig] int GetAutoArrange();
    [PreserveSig] int SelectItem(int index, uint flags);
    [PreserveSig]
    int SelectAndPositionItems(
        uint count,
        IntPtr pidls,
        IntPtr points,
        uint flags);
}

internal static class Program
{
    private const int GWL_STYLE = -16;
    private const long LVS_SORTASCENDING = 0x0010;
    private const long LVS_SORTDESCENDING = 0x0020;
    private const long LVS_AUTOARRANGE = 0x0100;
    private const uint LVM_FIRST = 0x1000;
    private const uint LVM_GETITEMCOUNT = LVM_FIRST + 4;
    private const uint LVM_GETITEMW = LVM_FIRST + 75;
    private const uint LVM_GETITEMPOSITION = LVM_FIRST + 16;
    private const uint LVM_GETITEMTEXTW = LVM_FIRST + 115;
    private const uint LVM_FINDITEMW = LVM_FIRST + 83;
    private const uint LVIF_PARAM = 0x0004;
    private const uint LVFI_PARAM = 0x0001;
    private const uint LVFI_STRING = 0x0002;
    private const uint WM_KEYDOWN = 0x0100;
    private const uint WM_KEYUP = 0x0101;
    private const int VK_F5 = 0x74;
    private const uint PROCESS_VM_OPERATION = 0x0008;
    private const uint PROCESS_VM_READ = 0x0010;
    private const uint PROCESS_VM_WRITE = 0x0020;
    private const uint MEM_COMMIT = 0x1000;
    private const uint MEM_RESERVE = 0x2000;
    private const uint MEM_RELEASE = 0x8000;
    private const uint PAGE_READWRITE = 0x04;
    private const int SM_CXICONSPACING = 38;
    private const int SM_CYICONSPACING = 39;
    private const uint SVSI_POSITIONITEM = 0x0080;

    [StructLayout(LayoutKind.Sequential)]
    private struct LVITEM
    {
        public uint mask;
        public int iItem;
        public int iSubItem;
        public uint state;
        public uint stateMask;
        public IntPtr pszText;
        public int cchTextMax;
        public int iImage;
        public IntPtr lParam;
        public int iIndent;
        public int iGroupId;
        public uint cColumns;
        public IntPtr puColumns;
        public IntPtr piColFmt;
        public int iGroup;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct RECT { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)]
    private struct POINT { public int X, Y; }
    [StructLayout(LayoutKind.Sequential)]
    private struct LVFINDINFO
    {
        public uint flags;
        public IntPtr psz;
        public IntPtr lParam;
        public POINT pt;
        public uint vkDirection;
    }

    private sealed class DesktopItem
    {
        public int Index;
        public string Name;
        public int Group;
        public int Priority;
        public string FileKind;
        public IntPtr Identity;
        public IntPtr Pidl;
        public int NameOccurrence;
        public bool IsWhitelisted;
        public bool IsOutsidePrimaryScreen;
        public string ParsingName;
        public ShellPoint CurrentPosition;
        public ShellPoint TargetPosition;
    }

    private sealed class LayoutPlan
    {
        public IntPtr ListView;
        public DesktopFolderView FolderView;
        public List<DesktopItem> AllItems;
        public List<DesktopItem> SortedItems;
        public int ProtectedCount;
        public int OutsidePrimaryCount;
        public int Rows;
        public int Columns;
        public int SpacingX;
        public int SpacingY;
    }

    private sealed class OperationResult
    {
        public int Arranged;
        public int Protected;
        public int Fixed;
        public int Restored;
        public int Skipped;
        public int Applications;
        public int Folders;
        public int Files;
        public bool BackupSaved;
        public string Details;
    }

    private sealed class LayoutRecord
    {
        public string ParsingName;
        public string Name;
        public int X;
        public int Y;
    }

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr FindWindowEx(IntPtr parent, IntPtr childAfter, string className, string windowName);
    [DllImport("user32.dll")]
    private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
    private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetClassName(IntPtr hWnd, StringBuilder className, int maxCount);
    [DllImport("user32.dll")]
    private static extern IntPtr SendMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    [DllImport("user32.dll")]
    private static extern bool GetClientRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")]
    private static extern bool ScreenToClient(IntPtr hWnd, ref POINT point);
    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    private static extern bool ShowWindow(IntPtr hWnd, int command);
    [DllImport("user32.dll")]
    private static extern bool ReleaseCapture();
    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);
    [DllImport("user32.dll", EntryPoint = "GetWindowLongPtr")]
    private static extern IntPtr GetWindowLongPtr64(IntPtr hWnd, int index);
    [DllImport("user32.dll", EntryPoint = "SetWindowLongPtr")]
    private static extern IntPtr SetWindowLongPtr64(IntPtr hWnd, int index, IntPtr value);
    [DllImport("user32.dll")]
    private static extern bool SetWindowPos(IntPtr hWnd, IntPtr insertAfter, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll")]
    private static extern int GetSystemMetrics(int index);
    [DllImport("user32.dll")]
    private static extern bool SetProcessDpiAwarenessContext(IntPtr dpiContext);
    [DllImport("user32.dll")]
    private static extern bool SetProcessDPIAware();
    [DllImport("kernel32.dll")]
    private static extern IntPtr OpenProcess(uint desiredAccess, bool inheritHandle, uint processId);
    [DllImport("kernel32.dll")]
    private static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll")]
    private static extern IntPtr VirtualAllocEx(IntPtr process, IntPtr address, UIntPtr size, uint allocationType, uint protect);
    [DllImport("kernel32.dll")]
    private static extern bool VirtualFreeEx(IntPtr process, IntPtr address, UIntPtr size, uint freeType);
    [DllImport("kernel32.dll")]
    private static extern bool WriteProcessMemory(IntPtr process, IntPtr address, byte[] buffer, int size, out IntPtr bytesWritten);
    [DllImport("kernel32.dll")]
    private static extern bool ReadProcessMemory(IntPtr process, IntPtr address, byte[] buffer, int size, out IntPtr bytesRead);
    [DllImport("shell32.dll")]
    private static extern void SHChangeNotify(uint eventId, uint flags, IntPtr item1, IntPtr item2);
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    private static extern bool SHGetPathFromIDList(IntPtr pidl, StringBuilder path);
    [DllImport("shell32.dll")]
    private static extern int SHGetKnownFolderIDList(ref Guid folderId, uint flags, IntPtr token, out IntPtr pidl);
    [DllImport("shell32.dll")]
    private static extern IntPtr ILCombine(IntPtr parentPidl, IntPtr childPidl);
    [DllImport("shell32.dll")]
    private static extern void ILFree(IntPtr pidl);
    [DllImport("shell32.dll")]
    private static extern int SHGetNameFromIDList(IntPtr pidl, uint displayNameType, out IntPtr name);

    [STAThread]
    private static void Main()
    {
        EnableDpiAwareness();
        bool ownsMutex;
        using (var mutex = new Mutex(true, @"Local\DesktopOrganizer.V2.SingleInstance", out ownsMutex))
        {
            if (!ownsMutex)
            {
                IntPtr existing = FindWindow(null, "一键整理桌面");
                if (existing != IntPtr.Zero)
                {
                    ShowWindow(existing, 9);
                    SetForegroundWindow(existing);
                }
                return;
            }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new OrganizerForm());
        }
    }

    private static void EnableDpiAwareness()
    {
        try
        {
            // Windows 10/11: keep window rectangles and IFolderView coordinates in the same physical-pixel space.
            if (SetProcessDpiAwarenessContext(new IntPtr(-4))) return; // DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        }
        catch (EntryPointNotFoundException) { }
        try { SetProcessDPIAware(); }
        catch (EntryPointNotFoundException) { }
    }

    private static void EnableRequiredSystemIcons()
    {
        string[] ids = {
            "{20D04FE0-3AEA-1069-A2D8-08002B30309D}", // This PC
            "{645FF040-5081-101B-9F08-00AA002F954E}", // Recycle Bin
            "{5399E694-6CE5-4D6C-8FCE-1D8870FDCBA0}"  // Control Panel
        };
        foreach (string branch in new[] { "NewStartPanel", "ClassicStartMenu" })
        using (RegistryKey key = Registry.CurrentUser.CreateSubKey(
            @"Software\Microsoft\Windows\CurrentVersion\Explorer\HideDesktopIcons\" + branch))
        {
            foreach (string id in ids) key.SetValue(id, 0, RegistryValueKind.DWord);
        }
    }

    private static IntPtr FindDesktopListView()
    {
        IntPtr progman = FindWindow("Progman", null);
        IntPtr defView = FindWindowEx(progman, IntPtr.Zero, "SHELLDLL_DefView", null);
        if (defView != IntPtr.Zero)
            return FindWindowEx(defView, IntPtr.Zero, "SysListView32", "FolderView");

        IntPtr result = IntPtr.Zero;
        EnumWindows((top, _) =>
        {
            IntPtr view = FindWindowEx(top, IntPtr.Zero, "SHELLDLL_DefView", null);
            if (view == IntPtr.Zero) return true;
            IntPtr list = FindWindowEx(view, IntPtr.Zero, "SysListView32", "FolderView");
            if (list == IntPtr.Zero) return true;
            result = list;
            return false;
        }, IntPtr.Zero);
        return result;
    }

    private static List<DesktopItem> ReadItems(IntPtr listView, DesktopFolderView folderView)
    {
        RECT desktopArea;
        if (!GetClientRect(listView, out desktopArea))
            throw new InvalidOperationException("无法读取桌面可用区域。");
        RECT primaryArea = GetPrimaryScreenClientArea(listView, desktopArea);
        int whitelistStart = primaryArea.Left + ((primaryArea.Right - primaryArea.Left) * 2) / 3;
        int itemCount = folderView.GetItemCount();
        Guid desktopFolderId = new Guid("B4BFCC3A-DB2C-424C-B029-7FE99A87C641");
        IntPtr desktopPidl;
        int rootResult = SHGetKnownFolderIDList(ref desktopFolderId, 0, IntPtr.Zero, out desktopPidl);
        if (rootResult < 0 || desktopPidl == IntPtr.Zero)
            throw new InvalidOperationException("无法读取 Windows 桌面标识（错误 0x" + rootResult.ToString("X8") + "）。");

        var items = new List<DesktopItem>();
        try
        {
            for (int i = 0; i < itemCount; i++)
            {
                IntPtr childPidl = IntPtr.Zero;
                IntPtr absolutePidl = IntPtr.Zero;
                IntPtr namePointer = IntPtr.Zero;
                IntPtr parsingPointer = IntPtr.Zero;
                try
                {
                    childPidl = folderView.GetItemPidl(i);
                    absolutePidl = ILCombine(desktopPidl, childPidl);
                    if (absolutePidl == IntPtr.Zero)
                        throw new InvalidOperationException("无法组合第 " + (i + 1) + " 个桌面图标的标识。");

                    int nameResult = SHGetNameFromIDList(absolutePidl, 0, out namePointer); // SIGDN_NORMALDISPLAY
                    if (nameResult < 0 || namePointer == IntPtr.Zero)
                        throw new InvalidOperationException("无法读取第 " + (i + 1) + " 个桌面图标的名称。");
                    string name = Marshal.PtrToStringUni(namePointer);
                    if (String.IsNullOrWhiteSpace(name))
                        throw new InvalidOperationException("第 " + (i + 1) + " 个桌面图标名称为空。");

                    var path = new StringBuilder(32768);
                    string sourcePath = SHGetPathFromIDList(absolutePidl, path) ? path.ToString() : null;
                    string parsingName = null;
                    if (SHGetNameFromIDList(absolutePidl, 0x80028000, out parsingPointer) >= 0 && parsingPointer != IntPtr.Zero)
                        parsingName = Marshal.PtrToStringUni(parsingPointer); // SIGDN_DESKTOPABSOLUTEPARSING
                    ShellPoint currentPosition;
                    if (!folderView.TryGetItemPosition(childPidl, out currentPosition))
                        throw new InvalidOperationException("无法读取桌面图标“" + name + "”的位置。");

                    DesktopItem item = Classify(i, name, childPidl, sourcePath);
                    item.Pidl = childPidl;
                    item.ParsingName = parsingName;
                    item.CurrentPosition = currentPosition;
                    childPidl = IntPtr.Zero; // Ownership is transferred to the DesktopItem.
                    // The three system icons stay fixed at the beginning even if moved accidentally.
                    item.IsOutsidePrimaryScreen = Screen.AllScreens.Length > 1 &&
                        (currentPosition.X < primaryArea.Left || currentPosition.X >= primaryArea.Right ||
                         currentPosition.Y < primaryArea.Top || currentPosition.Y >= primaryArea.Bottom);
                    item.IsWhitelisted = item.Priority >= 3 &&
                        (item.IsOutsidePrimaryScreen || currentPosition.X >= whitelistStart);
                    items.Add(item);
                }
                finally
                {
                    if (namePointer != IntPtr.Zero) Marshal.FreeCoTaskMem(namePointer);
                    if (parsingPointer != IntPtr.Zero) Marshal.FreeCoTaskMem(parsingPointer);
                    if (absolutePidl != IntPtr.Zero) ILFree(absolutePidl);
                    if (childPidl != IntPtr.Zero) Marshal.FreeCoTaskMem(childPidl);
                }
            }
            return items;
        }
        catch
        {
            foreach (DesktopItem item in items)
                if (item.Pidl != IntPtr.Zero) Marshal.FreeCoTaskMem(item.Pidl);
            throw;
        }
        finally { Marshal.FreeCoTaskMem(desktopPidl); }
    }

    private static RECT GetPrimaryScreenClientArea(IntPtr listView, RECT fallback)
    {
        if (Screen.AllScreens.Length <= 1) return fallback;
        Rectangle bounds = Screen.PrimaryScreen.WorkingArea;
        var topLeft = new POINT { X = bounds.Left, Y = bounds.Top };
        var bottomRight = new POINT { X = bounds.Right, Y = bounds.Bottom };
        if (!ScreenToClient(listView, ref topLeft) || !ScreenToClient(listView, ref bottomRight)) return fallback;
        return new RECT { Left = topLeft.X, Top = topLeft.Y, Right = bottomRight.X, Bottom = bottomRight.Y };
    }

    private static IntPtr ReadItemIdentity(IntPtr listView, IntPtr process, IntPtr remoteItem, int index, int itemBytes)
    {
        var request = new LVITEM { mask = LVIF_PARAM, iItem = index };
        IntPtr local = Marshal.AllocHGlobal(itemBytes);
        try
        {
            Marshal.StructureToPtr(request, local, false);
            byte[] requestBytes = new byte[itemBytes];
            Marshal.Copy(local, requestBytes, 0, itemBytes);
            IntPtr written;
            if (!WriteProcessMemory(process, remoteItem, requestBytes, requestBytes.Length, out written)) return IntPtr.Zero;
            SendMessage(listView, LVM_GETITEMW, IntPtr.Zero, remoteItem);
            byte[] responseBytes = new byte[itemBytes];
            IntPtr read;
            if (!ReadProcessMemory(process, remoteItem, responseBytes, responseBytes.Length, out read)) return IntPtr.Zero;
            Marshal.Copy(responseBytes, 0, local, itemBytes);
            return ((LVITEM)Marshal.PtrToStructure(local, typeof(LVITEM))).lParam;
        }
        finally { Marshal.FreeHGlobal(local); }
    }

    private static POINT ReadItemPosition(IntPtr listView, IntPtr process, IntPtr remotePoint, int index)
    {
        SendMessage(listView, LVM_GETITEMPOSITION, (IntPtr)index, remotePoint);
        int pointSize = Marshal.SizeOf(typeof(POINT));
        byte[] raw = new byte[pointSize];
        IntPtr read;
        if (!ReadProcessMemory(process, remotePoint, raw, raw.Length, out read)) return new POINT();
        IntPtr local = Marshal.AllocHGlobal(pointSize);
        try
        {
            Marshal.Copy(raw, 0, local, pointSize);
            return (POINT)Marshal.PtrToStructure(local, typeof(POINT));
        }
        finally { Marshal.FreeHGlobal(local); }
    }

    private static string TryGetPathFromRemotePidl(IntPtr process, IntPtr remotePidl)
    {
        if (remotePidl == IntPtr.Zero) return null;
        var bytes = new List<byte>();
        try
        {
            int offset = 0;
            for (int part = 0; part < 128; part++)
            {
                byte[] sizeBytes = new byte[2];
                IntPtr read;
                if (!ReadProcessMemory(process, IntPtr.Add(remotePidl, offset), sizeBytes, 2, out read)) return null;
                int size = sizeBytes[0] | (sizeBytes[1] << 8);
                if (size == 0) { bytes.AddRange(sizeBytes); break; }
                if (size < 2 || size > 1024 || bytes.Count + size > 32768) return null;
                byte[] partBytes = new byte[size];
                if (!ReadProcessMemory(process, IntPtr.Add(remotePidl, offset), partBytes, size, out read)) return null;
                bytes.AddRange(partBytes);
                offset += size;
            }
            if (bytes.Count < 2) return null;
            IntPtr localPidl = Marshal.AllocCoTaskMem(bytes.Count);
            try
            {
                Marshal.Copy(bytes.ToArray(), 0, localPidl, bytes.Count);
                var path = new StringBuilder(32768);
                return SHGetPathFromIDList(localPidl, path) ? path.ToString() : null;
            }
            finally { Marshal.FreeCoTaskMem(localPidl); }
        }
        catch { return null; }
    }

    private static DesktopItem Classify(int index, string name, IntPtr identity, string sourcePath)
    {
        string normalized = name.Trim();
        int priority = SpecialPriority(normalized);
        int group;
        string fileKind = "";
        if (priority < 3) group = 0;
        else
        {
            string path = sourcePath ?? FindDesktopEntry(normalized);
            if (path != null && Directory.Exists(path)) group = 1;
            else if (path != null && String.Equals(Path.GetExtension(path), ".lnk", StringComparison.OrdinalIgnoreCase))
            {
                string target = ResolveShortcutTarget(path);
                if (!String.IsNullOrEmpty(target) && Directory.Exists(target)) group = 2;
                else if (!String.IsNullOrEmpty(target) && !IsApplication(Path.GetExtension(target)))
                {
                    string targetExtension = Path.GetExtension(target);
                    group = FileGroup(targetExtension);
                    fileKind = FileKind(targetExtension);
                }
                else group = 0;
            }
            else if (path != null && IsApplication(Path.GetExtension(path))) group = 0;
            else if (path != null)
            {
                string extension = Path.GetExtension(path);
                group = FileGroup(extension);
                fileKind = FileKind(extension);
            }
            else group = 0; // Other shell objects, such as Network, are applications/system entries.
        }
        return new DesktopItem { Index = index, Name = normalized, Group = group, Priority = priority, FileKind = fileKind, Identity = identity };
    }

    private static int SpecialPriority(string name)
    {
        if (Matches(name, "此电脑", "This PC", "我的电脑", "Computer")) return 0;
        if (Matches(name, "回收站", "Recycle Bin")) return 1;
        if (Matches(name, "控制面板", "Control Panel")) return 2;
        return 3;
    }

    private static bool Matches(string name, params string[] choices)
    {
        return choices.Any(x => String.Equals(name, x, StringComparison.CurrentCultureIgnoreCase));
    }

    private static string FindDesktopEntry(string displayName)
    {
        string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        if (!Directory.Exists(desktop)) return null;
        try
        {
            string exact = Directory.EnumerateFileSystemEntries(desktop)
                .FirstOrDefault(path => String.Equals(Path.GetFileName(path), displayName, StringComparison.CurrentCultureIgnoreCase));
            if (exact != null) return exact;
            // Windows often hides known extensions on the desktop. Match that visible name too.
            return Directory.EnumerateFileSystemEntries(desktop)
                .FirstOrDefault(path => String.Equals(Path.GetFileNameWithoutExtension(path), displayName, StringComparison.CurrentCultureIgnoreCase));
        }
        catch { return null; }
    }

    // A displayed desktop name can represent both a folder and a hidden-extension
    // shortcut with the same label (for example, "work" and "work.lnk").
    // Resolve each occurrence against the real directory entries in a stable order.
    private sealed class DesktopPathResolver
    {
        private readonly Dictionary<string, List<string>> candidates = new Dictionary<string, List<string>>(StringComparer.CurrentCultureIgnoreCase);
        private readonly Dictionary<string, int> used = new Dictionary<string, int>(StringComparer.CurrentCultureIgnoreCase);

        public DesktopPathResolver()
        {
            string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            if (!Directory.Exists(desktop)) return;
            try
            {
                foreach (string path in Directory.EnumerateFileSystemEntries(desktop))
                {
                    Add(Path.GetFileName(path), path);
                    if (!Directory.Exists(path)) Add(Path.GetFileNameWithoutExtension(path), path);
                }
                foreach (List<string> list in candidates.Values)
                    list.Sort(CompareCandidates);
            }
            catch { }
        }

        public string Resolve(string displayName)
        {
            List<string> list;
            if (!candidates.TryGetValue(displayName, out list) || list.Count == 0) return null;
            int index;
            used.TryGetValue(displayName, out index);
            used[displayName] = index + 1;
            return list[Math.Min(index, list.Count - 1)];
        }

        private void Add(string key, string path)
        {
            if (String.IsNullOrWhiteSpace(key)) return;
            List<string> list;
            if (!candidates.TryGetValue(key, out list))
            {
                list = new List<string>();
                candidates[key] = list;
            }
            if (!list.Contains(path, StringComparer.CurrentCultureIgnoreCase)) list.Add(path);
        }

        private static int CompareCandidates(string left, string right)
        {
            int kindLeft = Directory.Exists(left) ? 0 : String.Equals(Path.GetExtension(left), ".lnk", StringComparison.OrdinalIgnoreCase) ? 1 : 2;
            int kindRight = Directory.Exists(right) ? 0 : String.Equals(Path.GetExtension(right), ".lnk", StringComparison.OrdinalIgnoreCase) ? 1 : 2;
            return kindLeft != kindRight ? kindLeft.CompareTo(kindRight) : StringComparer.CurrentCultureIgnoreCase.Compare(left, right);
        }
    }

    private static string ResolveShortcutTarget(string shortcutPath)
    {
        object shell = null;
        object shortcut = null;
        try
        {
            shell = Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));
            shortcut = shell.GetType().InvokeMember("CreateShortcut", System.Reflection.BindingFlags.InvokeMethod, null, shell, new object[] { shortcutPath });
            return shortcut.GetType().InvokeMember("TargetPath", System.Reflection.BindingFlags.GetProperty, null, shortcut, null) as string;
        }
        catch { return null; }
        finally
        {
            if (shortcut != null && Marshal.IsComObject(shortcut)) Marshal.FinalReleaseComObject(shortcut);
            if (shell != null && Marshal.IsComObject(shell)) Marshal.FinalReleaseComObject(shell);
        }
    }

    private static string FileKind(string extension)
    {
        extension = (extension ?? "").ToLowerInvariant();
        if (new[] { ".doc", ".docx", ".docm", ".rtf", ".txt" }.Contains(extension)) return "01-文字文档";
        if (new[] { ".pdf" }.Contains(extension)) return "02-PDF";
        if (new[] { ".ppt", ".pptx", ".pps", ".ppsx" }.Contains(extension)) return "03-演示文稿";
        if (new[] { ".xls", ".xlsx", ".xlsm", ".csv" }.Contains(extension)) return "04-表格";
        if (new[] { ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg" }.Contains(extension)) return "05-图片";
        if (new[] { ".mp4", ".mkv", ".avi", ".mov", ".wmv" }.Contains(extension)) return "06-视频";
        if (new[] { ".mp3", ".wav", ".flac", ".m4a", ".aac" }.Contains(extension)) return "07-音频";
        if (new[] { ".zip", ".rar", ".7z", ".tar", ".gz" }.Contains(extension)) return "08-压缩包";
        if (new[] { ".ai", ".psd", ".blend" }.Contains(extension)) return "09-设计项目";
        return "99-其他文件-" + extension;
    }

    private static int FileGroup(string extension)
    {
        string normalized = (extension ?? "").ToLowerInvariant();
        return new[] { ".zip", ".rar", ".7z", ".tar", ".gz" }.Contains(normalized) ? 3 : 4;
    }

    private static bool IsApplication(string extension)
    {
        string[] applications = { ".url", ".appref-ms", ".exe", ".com", ".msi", ".bat", ".cmd", ".ps1" };
        return applications.Any(x => String.Equals(extension, x, StringComparison.OrdinalIgnoreCase));
    }

    private static LayoutPlan CreatePlan(bool ensureSystemIcons)
    {
        if (ensureSystemIcons)
        {
            EnableRequiredSystemIcons();
            SHChangeNotify(0x08000000, 0, IntPtr.Zero, IntPtr.Zero);
            Thread.Sleep(700);
        }
        IntPtr listView = FindDesktopListView();
        if (listView == IntPtr.Zero)
            throw new InvalidOperationException("没有找到桌面图标区域。请先显示桌面后再试。");
        SendMessage(listView, WM_KEYDOWN, (IntPtr)VK_F5, IntPtr.Zero);
        SendMessage(listView, WM_KEYUP, (IntPtr)VK_F5, IntPtr.Zero);
        Thread.Sleep(ensureSystemIcons ? 500 : 180);

        DesktopFolderView folderView = DesktopFolderView.Open();
        List<DesktopItem> allItems = ReadItems(listView, folderView);
        if (allItems.Count == 0) throw new InvalidOperationException("未读取到桌面图标。");
        List<DesktopItem> items = allItems.Where(x => !x.IsWhitelisted)
            .OrderBy(x => x.Group).ThenBy(x => x.Priority).ThenBy(x => x.FileKind ?? "")
            .ThenBy(x => x.Name, new ChineseNameComparer()).ToList();

        var occurrences = new Dictionary<string, int>(StringComparer.CurrentCultureIgnoreCase);
        foreach (DesktopItem item in items)
        {
            int occurrence;
            occurrences.TryGetValue(item.Name, out occurrence);
            item.NameOccurrence = occurrence;
            occurrences[item.Name] = occurrence + 1;
        }

        RECT wholeArea;
        if (!GetClientRect(listView, out wholeArea)) throw new InvalidOperationException("无法读取桌面可用区域。");
        RECT area = GetPrimaryScreenClientArea(listView, wholeArea);
        int safeWidth = Math.Max(1, ((area.Right - area.Left) * 2) / 3);
        ShellPoint viewSpacing = folderView.GetSpacing();
        int spacingX = Math.Max(85, viewSpacing.X > 0 ? viewSpacing.X : GetSystemMetrics(SM_CXICONSPACING));
        int spacingY = Math.Max(90, viewSpacing.Y > 0 ? viewSpacing.Y : GetSystemMetrics(SM_CYICONSPACING));
        int rows = Math.Max(1, (area.Bottom - area.Top - 20) / spacingY);
        int columns = Math.Max(1, (safeWidth - 20) / spacingX);
        if (items.Count >= rows * columns)
            throw new InvalidOperationException("左侧整理区空间不足，本次操作已停止。右侧保留区没有被修改。");
        for (int position = 0; position < items.Count; position++)
            items[position].TargetPosition = new ShellPoint {
                X = area.Left + 10 + (position / rows) * spacingX,
                Y = area.Top + 10 + (position % rows) * spacingY
            };

        return new LayoutPlan {
            ListView = listView, FolderView = folderView, AllItems = allItems, SortedItems = items,
            ProtectedCount = allItems.Count(x => x.IsWhitelisted),
            OutsidePrimaryCount = allItems.Count(x => x.IsOutsidePrimaryScreen),
            Rows = rows, Columns = columns, SpacingX = spacingX, SpacingY = spacingY
        };
    }

    private static OperationResult OrganizeDesktop()
    {
        LayoutPlan plan = null;
        try
        {
            plan = CreatePlan(true);
            bool needsMovement = plan.SortedItems.Any(x => !IsNear(x.CurrentPosition, x.TargetPosition, plan.SpacingX, plan.SpacingY));
            if (needsMovement)
            {
                SaveLayout(plan.AllItems);
                DisableAutomaticArrange(plan.ListView);
                PositionItems(plan.FolderView, plan.SortedItems, plan.Rows, plan.Columns, plan.SpacingX, plan.SpacingY);
            }
            return new OperationResult {
                Arranged = plan.SortedItems.Count,
                Protected = plan.ProtectedCount,
                Fixed = plan.SortedItems.Count(x => x.Priority < 3),
                BackupSaved = needsMovement,
                Details = !needsMovement ? "当前布局已经符合规则，图标坐标保持不变。" :
                    plan.OutsidePrimaryCount > 0 ? "检测到其他显示器图标，已安全保留 " + plan.OutsidePrimaryCount + " 个。" : null
            };
        }
        finally { if (plan != null) FreeItems(plan.AllItems); }
    }

    private static OperationResult PreviewDesktop()
    {
        LayoutPlan plan = null;
        try
        {
            plan = CreatePlan(false);
            int applications = plan.SortedItems.Count(x => x.Group == 0);
            int folders = plan.SortedItems.Count(x => x.Group == 1);
            int shortcuts = plan.SortedItems.Count(x => x.Group == 2);
            int archives = plan.SortedItems.Count(x => x.Group == 3);
            int files = plan.SortedItems.Count(x => x.Group == 4);
            return new OperationResult {
                Arranged = plan.SortedItems.Count, Protected = plan.ProtectedCount,
                Applications = applications, Folders = folders + shortcuts, Files = archives + files,
                Details = "应用程序 " + applications + "  ·  文件夹 " + folders + "  ·  文件夹快捷方式 " + shortcuts +
                          "\n压缩文件 " + archives + "  ·  普通文件 " + files +
                          "\n需要网格 " + plan.SortedItems.Count + " / " + (plan.Rows * plan.Columns - 1)
            };
        }
        finally { if (plan != null) FreeItems(plan.AllItems); }
    }

    private static string DataDirectory
    {
        get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "DesktopOrganizer"); }
    }

    private static string LayoutPath { get { return Path.Combine(DataDirectory, "last-layout.dat"); } }

    private static void SaveLayout(List<DesktopItem> items)
    {
        Directory.CreateDirectory(DataDirectory);
        string temporary = LayoutPath + ".tmp";
        using (var writer = new StreamWriter(temporary, false, new UTF8Encoding(false)))
        {
            writer.WriteLine("DESKTOP_ORGANIZER_LAYOUT_V2");
            writer.WriteLine(DateTime.UtcNow.Ticks.ToString(CultureInfo.InvariantCulture));
            foreach (DesktopItem item in items.Where(x => !String.IsNullOrWhiteSpace(x.ParsingName)))
                writer.WriteLine(Encode(item.ParsingName) + "\t" + Encode(item.Name) + "\t" +
                    item.CurrentPosition.X.ToString(CultureInfo.InvariantCulture) + "\t" +
                    item.CurrentPosition.Y.ToString(CultureInfo.InvariantCulture));
        }
        File.Copy(temporary, LayoutPath, true);
        File.Delete(temporary);
    }

    private static List<LayoutRecord> LoadLayout()
    {
        if (!File.Exists(LayoutPath)) throw new InvalidOperationException("还没有可撤销的桌面布局。请先完成一次整理。");
        string[] lines = File.ReadAllLines(LayoutPath, Encoding.UTF8);
        if (lines.Length < 2 || lines[0] != "DESKTOP_ORGANIZER_LAYOUT_V2")
            throw new InvalidOperationException("上次布局备份无法识别，未对桌面做任何修改。");
        var result = new List<LayoutRecord>();
        for (int i = 2; i < lines.Length; i++)
        {
            string[] part = lines[i].Split('\t');
            int x, y;
            if (part.Length != 4 || !Int32.TryParse(part[2], NumberStyles.Integer, CultureInfo.InvariantCulture, out x) ||
                !Int32.TryParse(part[3], NumberStyles.Integer, CultureInfo.InvariantCulture, out y)) continue;
            try { result.Add(new LayoutRecord { ParsingName = Decode(part[0]), Name = Decode(part[1]), X = x, Y = y }); }
            catch (FormatException) { }
        }
        if (result.Count == 0) throw new InvalidOperationException("上次布局备份中没有可恢复的图标。");
        return result;
    }

    private static string Encode(string value) { return Convert.ToBase64String(Encoding.UTF8.GetBytes(value ?? "")); }
    private static string Decode(string value) { return Encoding.UTF8.GetString(Convert.FromBase64String(value)); }

    private static OperationResult RestoreDesktop()
    {
        List<LayoutRecord> records = LoadLayout();
        LayoutPlan plan = null;
        try
        {
            plan = CreatePlan(false);
            var current = plan.AllItems.Where(x => !String.IsNullOrWhiteSpace(x.ParsingName))
                .GroupBy(x => x.ParsingName, StringComparer.OrdinalIgnoreCase)
                .Where(x => x.Count() == 1).ToDictionary(x => x.Key, x => x.First(), StringComparer.OrdinalIgnoreCase);
            var matched = new List<DesktopItem>();
            var targets = new List<ShellPoint>();
            int skipped = 0;
            foreach (LayoutRecord record in records)
            {
                DesktopItem item;
                if (!current.TryGetValue(record.ParsingName, out item)) { skipped++; continue; }
                ShellPoint target = new ShellPoint { X = record.X, Y = record.Y };
                bool occupiedByUnmatched = plan.AllItems.Any(other => other != item &&
                    !records.Any(saved => String.Equals(saved.ParsingName, other.ParsingName, StringComparison.OrdinalIgnoreCase)) &&
                    IsNear(other.CurrentPosition, target, plan.SpacingX, plan.SpacingY));
                if (occupiedByUnmatched) { skipped++; continue; }
                matched.Add(item);
                targets.Add(target);
            }
            if (matched.Count == 0) throw new InvalidOperationException("没有找到可安全恢复的桌面图标，桌面未被修改。");
            DisableAutomaticArrange(plan.ListView);
            plan.FolderView.SelectAndPositionItems(matched.Select(x => x.Pidl).ToArray(), targets.ToArray(), SVSI_POSITIONITEM);
            Thread.Sleep(250);
            int restored = 0;
            for (int i = 0; i < matched.Count; i++)
            {
                ShellPoint actual;
                if (plan.FolderView.TryGetItemPosition(matched[i].Pidl, out actual) &&
                    IsNear(actual, targets[i], plan.SpacingX, plan.SpacingY)) restored++;
                else skipped++;
            }
            return new OperationResult { Restored = restored, Skipped = skipped };
        }
        finally { if (plan != null) FreeItems(plan.AllItems); }
    }

    private static string ExportDiagnostics()
    {
        LayoutPlan plan = null;
        try
        {
            plan = CreatePlan(false);
            Directory.CreateDirectory(DataDirectory);
            string path = Path.Combine(DataDirectory, "DesktopOrganizer-Diagnostics-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".txt");
            using (var writer = new StreamWriter(path, false, new UTF8Encoding(false)))
            {
                writer.WriteLine("一键整理桌面 V2 诊断信息");
                writer.WriteLine("生成时间: " + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss zzz"));
                writer.WriteLine("Windows: " + Environment.OSVersion.VersionString);
                writer.WriteLine("显示器数量: " + Screen.AllScreens.Length);
                writer.WriteLine("主显示器工作区: " + Screen.PrimaryScreen.WorkingArea);
                writer.WriteLine("桌面项目: " + plan.AllItems.Count);
                writer.WriteLine("Shell 图标间距: " + plan.SpacingX + " x " + plan.SpacingY);
                writer.WriteLine("主屏网格: " + plan.Rows + " x " + plan.Columns);
                writer.WriteLine("其他显示器安全保留: " + plan.OutsidePrimaryCount);
                writer.WriteLine();
                foreach (DesktopItem item in plan.AllItems)
                    writer.WriteLine(item.Name + " | " + CategoryName(item) + " | 当前=" + item.CurrentPosition.X + "," + item.CurrentPosition.Y +
                        " | 目标=" + item.TargetPosition.X + "," + item.TargetPosition.Y + " | 保留=" + item.IsWhitelisted +
                        " | 固定=" + (item.Priority < 3) + " | identity=" + HashIdentity(item.ParsingName));
            }
            return path;
        }
        finally { if (plan != null) FreeItems(plan.AllItems); }
    }

    private static string CategoryName(DesktopItem item)
    {
        if (item.Priority < 3) return "固定项目";
        return item.Group == 0 ? "应用程序" : item.Group == 1 ? "实体文件夹" : item.Group == 2 ? "文件夹快捷方式" :
            item.Group == 3 ? "压缩文件" : (String.IsNullOrEmpty(item.FileKind) ? "普通文件" : item.FileKind.Substring(Math.Min(3, item.FileKind.Length)));
    }

    private static string HashIdentity(string identity)
    {
        if (String.IsNullOrEmpty(identity)) return "none";
        using (SHA256 sha = SHA256.Create())
            return BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(identity))).Replace("-", "").Substring(0, 16);
    }

    private static void FreeItems(IEnumerable<DesktopItem> items)
    {
        if (items == null) return;
        foreach (DesktopItem item in items)
            if (item.Pidl != IntPtr.Zero) { Marshal.FreeCoTaskMem(item.Pidl); item.Pidl = IntPtr.Zero; }
    }

    private static void DisableAutomaticArrange(IntPtr listView)
    {
        long style = GetWindowLongPtr64(listView, GWL_STYLE).ToInt64();
        long newStyle = style & ~(LVS_AUTOARRANGE | LVS_SORTASCENDING | LVS_SORTDESCENDING);
        SetWindowLongPtr64(listView, GWL_STYLE, new IntPtr(newStyle));
        SetWindowPos(listView, IntPtr.Zero, 0, 0, 0, 0, 0x0020 | 0x0001 | 0x0002 | 0x0004 | 0x0020);
    }

    private static void PositionItems(DesktopFolderView folderView, List<DesktopItem> items, int rows, int columns, int spacingX, int spacingY)
    {
        if (items.Count == 0) return;
        var pidls = new IntPtr[items.Count];
        var points = new ShellPoint[items.Count];
        for (int position = 0; position < items.Count; position++)
        {
            pidls[position] = items[position].Pidl;
            points[position] = items[position].TargetPosition;
        }

        int mismatchCount = items.Count;
        for (int attempt = 0; attempt < 3; attempt++)
        {
            ArrangeWithSpareSlot(folderView, pidls, points, rows, columns, spacingX, spacingY);
            Thread.Sleep(200);
            mismatchCount = CountPositionMismatches(folderView, pidls, points, spacingX, spacingY);
            if (mismatchCount == 0) return;
        }

        throw new InvalidOperationException("Windows 桌面尚有 " + mismatchCount + " 个图标未到达目标位置，请稍后重试。");
    }

    private static void ArrangeWithSpareSlot(
        DesktopFolderView folderView,
        IntPtr[] pidls,
        ShellPoint[] expected,
        int rows,
        int columns,
        int spacingX,
        int spacingY)
    {
        var actual = new ShellPoint[pidls.Length];
        for (int i = 0; i < pidls.Length; i++)
            if (!folderView.TryGetItemPosition(pidls[i], out actual[i]))
                throw new InvalidOperationException("无法核对第 " + (i + 1) + " 个桌面图标的位置。");

        int originX = expected.Length > 0 ? expected[0].X : 10;
        int originY = expected.Length > 0 ? expected[0].Y : 10;
        ShellPoint empty = FindEmptyGridPoint(actual, rows, columns, spacingX, spacingY, originX, originY);
        for (int desiredIndex = 0; desiredIndex < pidls.Length; desiredIndex++)
        {
            if (IsNear(actual[desiredIndex], expected[desiredIndex], spacingX, spacingY)) continue;

            int occupant = FindOccupant(actual, expected[desiredIndex], desiredIndex, spacingX, spacingY);
            if (occupant >= 0)
                actual[occupant] = MoveItem(folderView, pidls[occupant], empty, spacingX, spacingY);

            ShellPoint newlyEmpty = actual[desiredIndex];
            actual[desiredIndex] = MoveItem(folderView, pidls[desiredIndex], expected[desiredIndex], spacingX, spacingY);
            empty = newlyEmpty;
        }
    }

    private static ShellPoint FindEmptyGridPoint(
        ShellPoint[] actual,
        int rows,
        int columns,
        int spacingX,
        int spacingY,
        int originX,
        int originY)
    {
        for (int column = columns - 1; column >= 0; column--)
        {
            for (int row = rows - 1; row >= 0; row--)
            {
                var candidate = new ShellPoint { X = originX + column * spacingX, Y = originY + row * spacingY };
                if (FindOccupant(actual, candidate, -1, spacingX, spacingY) < 0) return candidate;
            }
        }
        throw new InvalidOperationException("左侧整理区域没有找到可用于交换位置的空格。");
    }

    private static int FindOccupant(
        ShellPoint[] actual,
        ShellPoint target,
        int ignoredIndex,
        int spacingX,
        int spacingY)
    {
        for (int i = 0; i < actual.Length; i++)
            if (i != ignoredIndex && IsNear(actual[i], target, spacingX, spacingY)) return i;
        return -1;
    }

    private static ShellPoint MoveItem(
        DesktopFolderView folderView,
        IntPtr pidl,
        ShellPoint target,
        int spacingX,
        int spacingY)
    {
        ShellPoint actual = new ShellPoint();
        for (int attempt = 0; attempt < 3; attempt++)
        {
            folderView.SelectAndPositionItems(
                new[] { pidl }, new[] { target }, SVSI_POSITIONITEM);
            Thread.Sleep(attempt == 0 ? 20 : 80);
            if (folderView.TryGetItemPosition(pidl, out actual) && IsNear(actual, target, spacingX, spacingY))
                return actual;
        }
        throw new InvalidOperationException("Windows 没有把一个桌面图标移动到预定空格。");
    }

    private static bool IsNear(ShellPoint actual, ShellPoint expected, int spacingX, int spacingY)
    {
        return Math.Abs(actual.X - expected.X) <= Math.Max(16, spacingX / 3) &&
               Math.Abs(actual.Y - expected.Y) <= Math.Max(16, spacingY / 3);
    }

    private static int CountPositionMismatches(
        DesktopFolderView folderView,
        IntPtr[] pidls,
        ShellPoint[] expected,
        int spacingX,
        int spacingY)
    {
        int mismatches = 0;
        for (int i = 0; i < pidls.Length; i++)
        {
            ShellPoint actual;
            if (!folderView.TryGetItemPosition(pidls[i], out actual) ||
                !IsNear(actual, expected[i], spacingX, spacingY))
                mismatches++;
        }
        return mismatches;
    }

    private sealed class OrganizerForm : Form
    {
        private const int WindowLogicalWidth = 632;
        [StructLayout(LayoutKind.Sequential, CharSet = System.Runtime.InteropServices.CharSet.Auto)]
        private sealed class NativeFontDescription
        {
            public int Height, Width, Escapement, Orientation, Weight;
            public byte Italic, Underline, StrikeOut, CharSet, OutPrecision, ClipPrecision, Quality, PitchAndFamily;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string FaceName;
        }

        private readonly Color primary = Color.FromArgb(91, 108, 255);
        private readonly Panel titleBar = new Panel();
        private readonly Panel header = new Panel();
        private readonly Label appTitle = new Label();
        private readonly Label appSubtitle = new Label();
        private readonly Label statusEyebrow = new Label();
        private readonly Label statusTitle = new Label();
        private readonly Label statusBody = new Label();
        private readonly Label statusMeta = new Label();
        private readonly Label detailLabel = new Label();
        private readonly Panel statsPanel = new Panel();
        private readonly Label[] statValues = new Label[4];
        private readonly Label[] statLabels = new Label[4];
        private readonly AccentButton organizeButton;
        private readonly AccentButton undoButton;
        private readonly AccentButton previewButton;
        private readonly AccentButton diagnoseButton;
        private readonly AccentButton openBackupButton;
        private readonly Panel advancedPanel = new Panel();
        private readonly DisclosureButton advancedToggle;
        private readonly RoundedPanel statusCard;
        private readonly PictureBox iconBox;
        private readonly Button minimizeButton;
        private readonly Button closeButton;
        private readonly System.Windows.Forms.Timer motionTimer = new System.Windows.Forms.Timer();
        private int advancedFromHeight, advancedToHeight, advancedStarted;
        private int motionDeadline;
        private int statusTitleRestingTop;
        private bool advancedExpanded, advancedAnimating;
        private bool layingOut;
        private float successMotion = 1F;
        private int previewTarget;
        private int activeStatCount;
        private bool busy;

        public OrganizerForm()
        {
            Text = "一键整理桌面";
            BackColor = Color.FromArgb(246, 248, 252);
            ClientSize = new Size(WindowLogicalWidth, 560);
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.None;
            MaximizeBox = false;
            AutoScaleDimensions = new SizeF(96F, 96F);
            AutoScaleMode = AutoScaleMode.Dpi;
            Font = new Font("Microsoft YaHei UI", 10.5F, FontStyle.Regular, GraphicsUnit.Point);
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }

            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint, true);
            titleBar.BackColor = Color.FromArgb(249, 250, 253);
            var titleIcon = new PictureBox { SizeMode = PictureBoxSizeMode.Zoom };
            try { titleIcon.Image = Icon.ToBitmap(); } catch { }
            titleBar.Controls.Add(titleIcon);
            var windowTitle = new Label { Text = "一键整理桌面", ForeColor = Color.FromArgb(54, 60, 76), Font = new Font("Microsoft YaHei UI", 9.5F), AutoSize = false };
            titleBar.Controls.Add(windowTitle);
            minimizeButton = MakeTitleButton("—", false); minimizeButton.Click += delegate { WindowState = FormWindowState.Minimized; };
            closeButton = MakeTitleButton("×", true); closeButton.Click += delegate { Close(); };
            titleBar.Controls.Add(minimizeButton); titleBar.Controls.Add(closeButton);
            titleBar.MouseDown += delegate(object sender, MouseEventArgs e) { if (e.Button == MouseButtons.Left) { ReleaseCapture(); SendMessage(Handle, 0x00A1, (IntPtr)2, IntPtr.Zero); } };
            Controls.Add(titleBar);

            header.BackColor = BackColor;
            iconBox = new PictureBox { SizeMode = PictureBoxSizeMode.Zoom };
            try { iconBox.Image = Icon.ToBitmap(); } catch { }
            header.Controls.Add(iconBox);
            appTitle.Text = "一键整理桌面"; appTitle.AutoSize = false;
            appTitle.Font = CreateWeightedFont("Microsoft YaHei UI", 16.25F, 600); appTitle.ForeColor = Color.FromArgb(31, 36, 50);
            header.Controls.Add(appTitle);
            appSubtitle.Text = "按固定规则整理桌面图标，不移动真实文件"; appSubtitle.AutoSize = false;
            appSubtitle.Font = new Font("Microsoft YaHei UI", 10.5F); appSubtitle.ForeColor = Color.FromArgb(82, 92, 116);
            header.Controls.Add(appSubtitle);
            header.MouseMove += delegate(object sender, MouseEventArgs e) { iconBox.Left = Math.Max(U(0), Math.Min(U(2), (e.X - header.Width / 2) / Math.Max(1, U(120)))) + U(1); };
            header.MouseLeave += delegate { iconBox.Left = 0; };
            Controls.Add(header);

            organizeButton = new AccentButton(primary, true) {
                Text = "开始整理", Font = new Font("Microsoft YaHei UI", 12F, FontStyle.Regular), TabIndex = 0
            };
            organizeButton.Click += delegate { RunOperation("organize"); };
            Controls.Add(organizeButton);

            undoButton = new AccentButton(primary, false) {
                Text = "撤销上次整理", Font = new Font("Microsoft YaHei UI", 10F), TabIndex = 1, IconKind = 1
            };
            undoButton.Click += delegate { RunOperation("undo"); };
            Controls.Add(undoButton);
            previewButton = new AccentButton(primary, false) {
                Text = "预览整理", Font = new Font("Microsoft YaHei UI", 10F), TabIndex = 2, IconKind = 2
            };
            previewButton.Click += delegate { RunOperation("preview"); };
            Controls.Add(previewButton);

            statusCard = new RoundedPanel { BackColor = Color.White, BorderColor = Color.FromArgb(229, 233, 242) };
            statusEyebrow.AutoSize = false; statusEyebrow.Font = new Font("Microsoft YaHei UI", 9F);
            statusEyebrow.ForeColor = Color.FromArgb(111, 119, 138); statusCard.Controls.Add(statusEyebrow);
            statusTitle.AutoSize = false; statusTitle.Font = new Font("Microsoft YaHei UI", 14.5F, FontStyle.Bold);
            statusTitle.ForeColor = Color.FromArgb(38, 44, 60); statusCard.Controls.Add(statusTitle);
            statusBody.AutoSize = false; statusBody.Font = new Font("Microsoft YaHei UI", 10.5F);
            statusBody.ForeColor = Color.FromArgb(83, 91, 110); statusCard.Controls.Add(statusBody);
            statsPanel.BackColor = Color.White;
            for (int i = 0; i < statValues.Length; i++)
            {
                statValues[i] = new Label { AutoSize = false, TextAlign = ContentAlignment.MiddleCenter, Font = new Font("Microsoft YaHei UI", 14F, FontStyle.Bold), ForeColor = Color.FromArgb(55, 64, 92) };
                statLabels[i] = new Label { AutoSize = false, TextAlign = ContentAlignment.TopCenter, Font = new Font("Microsoft YaHei UI", 9F), ForeColor = Color.FromArgb(111, 119, 138) };
                statsPanel.Controls.Add(statValues[i]); statsPanel.Controls.Add(statLabels[i]);
            }
            statusCard.Controls.Add(statsPanel);
            statusMeta.AutoSize = false; statusMeta.Font = new Font("Microsoft YaHei UI", 9.5F);
            statusMeta.ForeColor = Color.FromArgb(101, 110, 130); statusCard.Controls.Add(statusMeta);
            detailLabel.AutoSize = false; detailLabel.AutoEllipsis = false; detailLabel.Font = new Font("Microsoft YaHei UI", 9.5F);
            detailLabel.ForeColor = Color.FromArgb(86, 126, 102); statusCard.Controls.Add(detailLabel);
            Controls.Add(statusCard);

            advancedToggle = new DisclosureButton { Text = "高级选项", TabIndex = 3 };
            advancedToggle.Click += delegate { ToggleAdvanced(); };
            Controls.Add(advancedToggle);

            advancedPanel.BackColor = BackColor; advancedPanel.Visible = false;
            diagnoseButton = new AccentButton(primary, false) { Text = "导出诊断信息", Font = new Font("Microsoft YaHei UI", 9.5F), TabIndex = 4 };
            diagnoseButton.Click += delegate { RunOperation("diagnose"); };
            advancedPanel.Controls.Add(diagnoseButton);
            openBackupButton = new AccentButton(primary, false) { Text = "打开布局备份目录", Font = new Font("Microsoft YaHei UI", 9.5F), TabIndex = 5 };
            openBackupButton.Click += delegate {
                try { Directory.CreateDirectory(DataDirectory); Process.Start("explorer.exe", DataDirectory); }
                catch (Exception ex) { ShowError(ex.Message); }
            };
            advancedPanel.Controls.Add(openBackupButton);
            Controls.Add(advancedPanel);

            AcceptButton = organizeButton;
            motionTimer.Interval = 16; motionTimer.Tick += MotionTick;
            organizeButton.MotionRequested = undoButton.MotionRequested = previewButton.MotionRequested = diagnoseButton.MotionRequested = openBackupButton.MotionRequested = statusCard.MotionRequested = advancedToggle.MotionRequested = EnsureMotion;
            SetReady();
            Shown += delegate {
                try { int preference = 2; DwmSetWindowAttribute(Handle, 33, ref preference, sizeof(int)); } catch { }
                ReflowAll();
            };
        }

        private int U(int logical)
        {
            return Math.Max(logical == 0 ? 0 : 1, (int)Math.Round(logical * DeviceDpi / 96F));
        }

        private static Font CreateWeightedFont(string family, float size, int weight)
        {
            using (var source = new Font(family, size, FontStyle.Regular, GraphicsUnit.Point))
            {
                try
                {
                    var description = new NativeFontDescription();
                    source.ToLogFont(description);
                    description.Weight = weight;
                    return Font.FromLogFont(description);
                }
                catch { return new Font(family, size, FontStyle.Regular, GraphicsUnit.Point); }
            }
        }

        private Button MakeTitleButton(string text, bool close)
        {
            var button = new Button { Text = text, FlatStyle = FlatStyle.Flat, BackColor = Color.FromArgb(249, 250, 253), ForeColor = Color.FromArgb(65, 70, 84), Font = new Font("Segoe UI", 12F), TabStop = false };
            button.FlatAppearance.BorderSize = 0; button.FlatAppearance.MouseOverBackColor = close ? Color.FromArgb(224, 76, 86) : Color.FromArgb(235, 237, 243); button.FlatAppearance.MouseDownBackColor = close ? Color.FromArgb(199, 57, 67) : Color.FromArgb(224, 227, 234);
            if (close) button.MouseEnter += delegate { button.ForeColor = Color.White; };
            button.MouseLeave += delegate { button.ForeColor = Color.FromArgb(65, 70, 84); };
            return button;
        }

        private int MeasureLabel(Label label, int width)
        {
            if (String.IsNullOrWhiteSpace(label.Text)) return 0;
            Size measured = TextRenderer.MeasureText(label.Text, label.Font, new Size(Math.Max(1, width), Int32.MaxValue),
                TextFormatFlags.WordBreak | TextFormatFlags.NoPrefix | TextFormatFlags.TextBoxControl);
            return measured.Height + U(2);
        }

        private void PlaceLabel(Label label, int left, ref int y, int width, int gapAfter)
        {
            if (String.IsNullOrWhiteSpace(label.Text)) { label.Visible = false; return; }
            label.Visible = true;
            int height = MeasureLabel(label, width);
            label.SetBounds(left, y, width, height);
            y += height + gapAfter;
        }

        private void ConfigureStats(string[] labels, string[] values)
        {
            activeStatCount = labels == null ? 0 : Math.Min(4, labels.Length);
            for (int i = 0; i < statValues.Length; i++)
            {
                bool visible = i < activeStatCount;
                statValues[i].Visible = statLabels[i].Visible = visible;
                statValues[i].Text = visible && values != null && i < values.Length ? values[i] : "";
                statLabels[i].Text = visible ? labels[i] : "";
            }
            statsPanel.Visible = activeStatCount > 0;
        }

        private void LayoutStats(int width)
        {
            if (activeStatCount == 0) return;
            int slot = width / activeStatCount;
            int valueHeight = U(30);
            int labelTop = valueHeight + U(2);
            int labelHeight = U(24);
            for (int i = 0; i < activeStatCount; i++)
            {
                int left = i * slot;
                int currentWidth = i == activeStatCount - 1 ? width - left : slot;
                statValues[i].SetBounds(left, 0, currentWidth, valueHeight);
                statLabels[i].SetBounds(left, labelTop, currentWidth, labelHeight);
            }
            statsPanel.Size = new Size(width, labelTop + labelHeight);
        }

        private void LayoutStatusCard()
        {
            int paddingX = U(26);
            int paddingTop = U(22);
            int contentWidth = statusCard.ClientSize.Width - paddingX * 2;
            int y = paddingTop;
            PlaceLabel(statusEyebrow, paddingX, ref y, contentWidth, U(6));
            statusTitleRestingTop = y;
            PlaceLabel(statusTitle, paddingX, ref y, contentWidth, U(10));
            PlaceLabel(statusBody, paddingX, ref y, contentWidth, U(14));
            if (activeStatCount > 0)
            {
                LayoutStats(contentWidth);
                statsPanel.Location = new Point(paddingX, y);
                y += statsPanel.Height + U(14);
            }
            PlaceLabel(statusMeta, paddingX, ref y, contentWidth, U(14));
            PlaceLabel(detailLabel, paddingX, ref y, contentWidth, 0);
            statusCard.Height = y + U(22);
        }

        private void ReflowAll()
        {
            if (layingOut) return;
            layingOut = true;
            try
            {
                int width = U(WindowLogicalWidth);
                int outer = U(36);
                int contentWidth = width - outer * 2;
                ClientSize = new Size(width, ClientSize.Height);
                titleBar.SetBounds(0, 0, width, U(44));
                Control titleIcon = titleBar.Controls[0];
                titleIcon.SetBounds(U(15), U(10), U(24), U(24));
                titleBar.Controls[1].SetBounds(U(47), U(10), U(210), U(24));
                minimizeButton.SetBounds(width - U(88), 0, U(44), U(44));
                closeButton.SetBounds(width - U(44), 0, U(44), U(44));

                int headerTextLeft = U(66);
                int headerTextWidth = contentWidth - headerTextLeft;
                int titleHeight = MeasureLabel(appTitle, headerTextWidth);
                int subtitleHeight = MeasureLabel(appSubtitle, headerTextWidth);
                int titleSubtitleGap = U(6);
                int textGroupHeight = titleHeight + titleSubtitleGap + subtitleHeight;
                int logoSize = U(46);
                int headerHeight = Math.Max(logoSize, textGroupHeight);
                header.SetBounds(outer, U(61), contentWidth, headerHeight);
                int textTop = Math.Max(0, (headerHeight - textGroupHeight) / 2);
                iconBox.SetBounds(0, Math.Max(0, (headerHeight - logoSize) / 2), logoSize, logoSize);
                appTitle.SetBounds(headerTextLeft, textTop, headerTextWidth, titleHeight);
                appSubtitle.SetBounds(headerTextLeft, textTop + titleHeight + titleSubtitleGap, headerTextWidth, subtitleHeight);

                organizeButton.SetBounds(outer, header.Bottom + U(16), contentWidth, U(56));
                int secondaryGap = U(16);
                int secondaryWidth = (contentWidth - secondaryGap) / 2;
                int secondaryTop = organizeButton.Bottom + U(16);
                undoButton.SetBounds(outer, secondaryTop, secondaryWidth, U(46));
                previewButton.SetBounds(outer + secondaryWidth + secondaryGap, secondaryTop, contentWidth - secondaryWidth - secondaryGap, U(46));

                statusCard.SetBounds(outer, undoButton.Bottom + U(20), contentWidth, Math.Max(statusCard.Height, U(180)));
                LayoutStatusCard();
                advancedToggle.SetBounds(outer, statusCard.Bottom + U(12), U(154), U(32));
                advancedPanel.SetBounds(outer, advancedToggle.Bottom + U(8), contentWidth, U(46));
                int advancedGap = U(16);
                int advancedButtonWidth = (contentWidth - advancedGap) / 2;
                diagnoseButton.SetBounds(0, 0, advancedButtonWidth, U(44));
                openBackupButton.SetBounds(advancedButtonWidth + advancedGap, 0, contentWidth - advancedButtonWidth - advancedGap, U(44));
                if (!advancedAnimating) ClientSize = new Size(width, DesiredWindowHeight(advancedExpanded));
            }
            finally { layingOut = false; }
        }

        private int DesiredWindowHeight(bool expanded)
        {
            return (expanded ? advancedPanel.Bottom : advancedToggle.Bottom) + U(20);
        }

        private void ApplyStatus(string eyebrow, string title, string body, string meta, string detail, Color titleColor, Color detailColor, string[] labels, string[] values)
        {
            statusEyebrow.Text = eyebrow;
            statusTitle.Text = title;
            statusBody.Text = body ?? "";
            statusMeta.Text = meta ?? "";
            detailLabel.Text = detail ?? "";
            statusTitle.ForeColor = titleColor;
            detailLabel.ForeColor = detailColor;
            ConfigureStats(labels, values);
            ReflowAll();
        }

        private void ToggleAdvanced()
        {
            if (advancedAnimating) return;
            advancedExpanded = !advancedExpanded;
            advancedToggle.Expanded = advancedExpanded;
            advancedFromHeight = ClientSize.Height;
            advancedToHeight = DesiredWindowHeight(advancedExpanded);
            advancedStarted = Environment.TickCount; advancedAnimating = true;
            EnsureMotion();
            if (advancedExpanded) advancedPanel.Visible = true;
        }

        private void MotionTick(object sender, EventArgs e)
        {
            organizeButton.Advance(); undoButton.Advance(); previewButton.Advance(); diagnoseButton.Advance(); openBackupButton.Advance(); statusCard.Advance(); advancedToggle.Advance();
            if (successMotion < 1F)
            {
                successMotion = Math.Min(1F, successMotion + .055F);
                statusTitle.Top = statusTitleRestingTop + (int)((1F - successMotion) * U(4));
                if (previewTarget > 0) statusTitle.Text = "预计整理 " + (int)(previewTarget * (1F - (float)Math.Pow(1F-successMotion, 3))) + " 个图标";
                statusTitle.Invalidate();
            }
            if (advancedAnimating)
            {
                float t = Math.Min(1F, (Environment.TickCount - advancedStarted) / 220F);
                float eased = 1F - (float)Math.Pow(1F - t, 3);
                ClientSize = new Size(U(WindowLogicalWidth), advancedFromHeight + (int)((advancedToHeight - advancedFromHeight) * eased));
                if (t >= 1F) { advancedAnimating = false; if (!advancedExpanded) advancedPanel.Visible = false; }
            }
            if (!advancedAnimating && successMotion >= 1F && (Environment.TickCount >= motionDeadline || (!organizeButton.NeedsAnimation && !undoButton.NeedsAnimation && !previewButton.NeedsAnimation && !diagnoseButton.NeedsAnimation && !openBackupButton.NeedsAnimation && !statusCard.NeedsAnimation && !advancedToggle.NeedsAnimation)))
                motionTimer.Stop();
        }

        private void EnsureMotion() { motionDeadline = Environment.TickCount + 650; if (!motionTimer.Enabled) motionTimer.Start(); }

        private void SetReady()
        {
            previewTarget = 0; successMotion = 1F;
            ApplyStatus("当前状态", "准备就绪", "点击开始后，将按固定规则整理桌面图标。",
                "排列方式    从上到下，再从左到右\n保留区域    右侧 1/3",
                "✓ 不会移动、删除或重命名任何桌面文件", Color.FromArgb(38, 44, 60), Color.FromArgb(86, 126, 102), null, null);
        }

        private void RunOperation(string kind)
        {
            if (busy) return;
            busy = true;
            SetButtons(false);
            previewTarget = 0; successMotion = 1F;
            string title = kind == "organize" ? "正在整理…" : kind == "undo" ? "正在恢复…" : kind == "preview" ? "正在预览…" : "正在生成诊断…";
            string body = kind == "organize" ? "正在读取桌面图标并计算安全位置…" : "正在读取当前桌面布局…";
            ApplyStatus("正在处理", title, body, "请稍候，窗口会在操作完成后自动更新。", "", primary, Color.FromArgb(86, 126, 102), null, null);
            var thread = new Thread(delegate()
            {
                try
                {
                    OperationResult result = null;
                    string path = null;
                    if (kind == "organize") result = OrganizeDesktop();
                    else if (kind == "undo") result = RestoreDesktop();
                    else if (kind == "preview") result = PreviewDesktop();
                    else path = ExportDiagnostics();
                    BeginInvoke((MethodInvoker)delegate { ShowSuccess(kind, result, path); });
                }
                catch (Exception ex)
                {
                    BeginInvoke((MethodInvoker)delegate {
                        if (kind == "undo" && ex.Message.IndexOf("还没有可撤销", StringComparison.Ordinal) >= 0) ShowNoUndoInfo();
                        else ShowError(ex.Message);
                    });
                }
            });
            thread.IsBackground = true;
            thread.SetApartmentState(ApartmentState.STA);
            thread.Start();
        }

        private void ShowSuccess(string kind, OperationResult result, string path)
        {
            busy = false; SetButtons(true);
            successMotion = 0F; previewTarget = 0;
            Color success = Color.FromArgb(42, 133, 84);
            if (kind == "organize")
            {
                string meta = result.BackupSaved ? "整理前布局已保存，可随时撤销。" : "未检测到坐标变化，保留了之前的撤销备份。";
                string detail = String.IsNullOrEmpty(result.Details) ? "✓ 没有移动任何桌面文件" : result.Details;
                ApplyStatus("整理完成", "桌面已整理好", "", meta, detail, success, Color.FromArgb(86, 126, 102),
                    new[] { "已整理", "保留未动", "固定项目" }, new[] { result.Arranged.ToString(), result.Protected.ToString(), result.Fixed.ToString() });
            }
            else if (kind == "undo")
            {
                ApplyStatus("撤销完成", "已恢复上次布局", "", "不存在或无法精确匹配的项目不会被移动。", "新出现的桌面项目保持原位。", success, Color.FromArgb(86, 126, 102),
                    new[] { "已恢复", "已跳过" }, new[] { result.Restored.ToString(), result.Skipped.ToString() });
            }
            else if (kind == "preview")
            {
                previewTarget = result.Arranged;
                ApplyStatus("整理预览", "预计整理 0 个图标", "以下为本次整理统计。", "", "本次预览没有移动任何图标。", success, Color.FromArgb(86, 126, 102),
                    new[] { "应用程序", "文件夹", "文件", "保留区" }, new[] { result.Applications.ToString(), result.Folders.ToString(), result.Files.ToString(), result.Protected.ToString() });
            }
            else
            {
                ApplyStatus("诊断完成", "诊断信息已导出", path, "身份仅记录短哈希，不包含完整路径。", "", success, Color.FromArgb(86, 126, 102), null, null);
            }
            EnsureMotion();
        }

        private void ShowNoUndoInfo()
        {
            previewTarget = 0; successMotion = 0F;
            busy = false; SetButtons(true);
            ApplyStatus("提示", "暂无可撤销的布局", "当前没有可恢复的桌面布局。完成一次有效整理后，即可使用撤销功能。",
                "桌面当前状态没有发生改变。", "", Color.FromArgb(72, 92, 132), Color.FromArgb(86, 126, 102), null, null);
            EnsureMotion();
        }

        private void ShowError(string message)
        {
            previewTarget = 0; successMotion = 0F;
            busy = false; SetButtons(true);
            Color error = Color.FromArgb(190, 67, 67);
            ApplyStatus("操作未完成", "无法安全完成操作", message, "桌面真实文件没有被移动、删除或重命名。",
                "如问题持续，可在高级选项中导出诊断信息。", error, error, null, null);
            EnsureMotion();
        }

        private void SetButtons(bool enabled)
        {
            organizeButton.Enabled = enabled; undoButton.Enabled = enabled; previewButton.Enabled = enabled; advancedToggle.Enabled = enabled;
            diagnoseButton.Enabled = enabled; openBackupButton.Enabled = enabled;
            organizeButton.Text = enabled ? "开始整理" : "正在处理…";
        }
    }

    private sealed class DisclosureButton : Button
    {
        private bool hovered;
        private float hoverAmount;
        public bool Expanded { get; set; }
        public Action MotionRequested { get; set; }
        public bool NeedsAnimation { get { return Math.Abs((hovered ? 1F : 0F) - hoverAmount) > .002F; } }

        public DisclosureButton()
        {
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint | ControlStyles.SupportsTransparentBackColor, true);
            FlatStyle = FlatStyle.Flat; FlatAppearance.BorderSize = 0; BackColor = Color.Transparent;
            ForeColor = Color.FromArgb(76, 86, 112); Font = new Font("Microsoft YaHei UI", 9.5F); Cursor = Cursors.Hand;
        }

        protected override void OnMouseEnter(EventArgs e) { hovered = true; if (MotionRequested != null) MotionRequested(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { hovered = false; if (MotionRequested != null) MotionRequested(); base.OnMouseLeave(e); }
        public void Advance()
        {
            float target = hovered ? 1F : 0F;
            float next = hoverAmount + (target - hoverAmount) * .18F;
            if (Math.Abs(next - hoverAmount) > .002F) { hoverAmount = next; Invalidate(); }
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.Clear(Parent == null ? Color.Transparent : Parent.BackColor);
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            Color textColor = Blend(ForeColor, Color.FromArgb(44, 55, 91), hoverAmount);
            Rectangle textBounds = new Rectangle(0, 0, Width - 24, Height);
            TextRenderer.DrawText(e.Graphics, Text, Font, textBounds, Enabled ? textColor : Color.FromArgb(145, 150, 163), TextFormatFlags.Left | TextFormatFlags.VerticalCenter | TextFormatFlags.SingleLine);
            int centerX = Math.Min(Width - 12, TextRenderer.MeasureText(Text, Font, new Size(Int32.MaxValue, Height), TextFormatFlags.NoPadding).Width + 13);
            int centerY = Height / 2;
            using (var pen = new Pen(Enabled ? textColor : Color.FromArgb(145, 150, 163), 1.5F))
            {
                pen.StartCap = pen.EndCap = LineCap.Round;
                if (Expanded) { e.Graphics.DrawLine(pen, centerX - 4, centerY + 2, centerX, centerY - 2); e.Graphics.DrawLine(pen, centerX, centerY - 2, centerX + 4, centerY + 2); }
                else { e.Graphics.DrawLine(pen, centerX - 4, centerY - 2, centerX, centerY + 2); e.Graphics.DrawLine(pen, centerX, centerY + 2, centerX + 4, centerY - 2); }
            }
            if (Focused && ShowFocusCues)
            {
                using (var pen = new Pen(Color.FromArgb(130, 143, 226))) { pen.DashStyle = DashStyle.Dot; e.Graphics.DrawRectangle(pen, 0, 2, Math.Max(1, centerX + 10), Math.Max(1, Height - 5)); }
            }
        }
    }

    private sealed class RoundedPanel : Panel
    {
        public Color BorderColor { get; set; }
        private bool hovered;
        private float hoverAmount;
        public Action MotionRequested { get; set; }
        public bool NeedsAnimation { get { return Math.Abs((hovered ? 1F : 0F) - hoverAmount) > .002F; } }
        public RoundedPanel() { SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint, true); }
        protected override void OnMouseEnter(EventArgs e) { hovered = true; if (MotionRequested != null) MotionRequested(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { hovered = false; if (MotionRequested != null) MotionRequested(); base.OnMouseLeave(e); }
        public void Advance() { float target = hovered ? 1F : 0F; float next = hoverAmount + (target - hoverAmount) * .18F; if (Math.Abs(next - hoverAmount) > .002F) { hoverAmount = next; Invalidate(); } }
        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            using (GraphicsPath path = RoundPath(new Rectangle(0, 0, Width - 1, Height - 1), 14))
            using (var pen = new Pen(Blend(BorderColor, Color.FromArgb(171, 181, 245), hoverAmount))) e.Graphics.DrawPath(pen, path);
        }
    }

    private sealed class AccentButton : Button
    {
        private readonly Color accent;
        private readonly bool filled;
        private bool hovered;
        private bool pressed;
        private float hoverAmount, pressAmount;
        private Point targetGlow, currentGlow;
        public int IconKind { get; set; }
        public Action MotionRequested { get; set; }
        public bool NeedsAnimation { get { return Math.Abs((hovered?1F:0F)-hoverAmount)>.002F || Math.Abs((pressed?1F:0F)-pressAmount)>.002F || currentGlow != targetGlow; } }
        public AccentButton(Color accent, bool filled)
        {
            this.accent = accent; this.filled = filled;
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint | ControlStyles.SupportsTransparentBackColor, true);
            FlatStyle = FlatStyle.Flat; FlatAppearance.BorderSize = 0; Cursor = Cursors.Hand;
            ForeColor = filled ? Color.White : Color.FromArgb(72, 78, 132); BackColor = Color.Transparent; UseVisualStyleBackColor = false;
        }
        protected override void OnMouseEnter(EventArgs e) { hovered = true; if (MotionRequested != null) MotionRequested(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { hovered = false; pressed = false; if (MotionRequested != null) MotionRequested(); base.OnMouseLeave(e); }
        protected override void OnMouseDown(MouseEventArgs e) { pressed = true; if (MotionRequested != null) MotionRequested(); base.OnMouseDown(e); }
        protected override void OnMouseUp(MouseEventArgs e) { pressed = false; if (MotionRequested != null) MotionRequested(); base.OnMouseUp(e); }
        protected override void OnMouseMove(MouseEventArgs e) { targetGlow = e.Location; if (MotionRequested != null) MotionRequested(); base.OnMouseMove(e); }
        protected override void OnResize(EventArgs e) { base.OnResize(e); Region = new Region(RoundPath(new Rectangle(0, 0, Width, Height), 12)); }
        public void Advance()
        {
            float h = hovered ? 1F : 0F, p = pressed ? 1F : 0F;
            float nh = hoverAmount + (h - hoverAmount) * .18F, np = pressAmount + (p - pressAmount) * .3F;
            int dx = targetGlow.X - currentGlow.X, dy = targetGlow.Y - currentGlow.Y;
            Point nextGlow = new Point(Math.Abs(dx) <= 5 ? targetGlow.X : currentGlow.X + (int)(dx * .18F), Math.Abs(dy) <= 5 ? targetGlow.Y : currentGlow.Y + (int)(dy * .18F));
            bool changed = Math.Abs(nh-hoverAmount)>.002F || Math.Abs(np-pressAmount)>.002F || nextGlow != currentGlow;
            currentGlow = nextGlow;
            if (changed) { hoverAmount=nh; pressAmount=np; Invalidate(); }
        }
        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.Clear(Parent == null ? Color.Transparent : Parent.BackColor);
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            int offset = pressAmount > .45F ? 1 : 0;
            Rectangle bounds = new Rectangle(0, offset, Width - 1, Height - 1 - offset);
            Color baseColor = !Enabled ? Color.FromArgb(188, 193, 207) : Blend(accent, Color.FromArgb(102, 98, 235), hoverAmount * .45F);
            using (GraphicsPath path = RoundPath(bounds, 12))
            {
                if (filled)
                {
                    using (var brush = new LinearGradientBrush(bounds, baseColor, Color.FromArgb(baseColor.A, Math.Max(0, baseColor.R - 18), Math.Max(0, baseColor.G - 10), baseColor.B), 0F))
                        e.Graphics.FillPath(brush, path);
                    if (hoverAmount > .01F)
                    {
                        Rectangle glow = new Rectangle(currentGlow.X - 115, currentGlow.Y - 55, 230, 110);
                        using (GraphicsPath ellipse = new GraphicsPath())
                        { ellipse.AddEllipse(glow); using (var light = new PathGradientBrush(ellipse)) { light.CenterColor = Color.FromArgb((int)(32 * hoverAmount), Color.White); light.SurroundColors = new[] { Color.FromArgb(0, Color.White) }; e.Graphics.SetClip(path); e.Graphics.FillEllipse(light, glow); e.Graphics.ResetClip(); } }
                    }
                }
                else
                {
                    using (var brush = new SolidBrush(hovered ? Color.FromArgb(245, 246, 255) : Color.White)) e.Graphics.FillPath(brush, path);
                    using (var pen = new Pen(Enabled ? Color.FromArgb(210, 215, 235) : Color.FromArgb(225, 227, 233))) e.Graphics.DrawPath(pen, path);
                }
                Rectangle textBounds = bounds;
                if (IconKind > 0) { DrawSmallIcon(e.Graphics, IconKind, new Point(Width / 2 - 60, Height / 2)); textBounds.X += 13; }
                TextRenderer.DrawText(e.Graphics, Text, Font, textBounds, Enabled ? ForeColor : Color.FromArgb(145, 150, 163),
                    TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.SingleLine);
                if (Focused && ShowFocusCues)
                {
                    Rectangle focus = Rectangle.Inflate(bounds, -5, -5);
                    using (var focusPen = new Pen(Color.FromArgb(125, 132, 238))) using (GraphicsPath focusPath = RoundPath(focus, 8)) { focusPen.Width = 1.5F; e.Graphics.DrawPath(focusPen, focusPath); }
                }
            }
        }
        private void DrawSmallIcon(Graphics g, int kind, Point center)
        {
            using (var pen = new Pen(Enabled ? ForeColor : Color.Gray, 1.5F))
            {
                pen.StartCap = pen.EndCap = LineCap.Round;
                if (kind == 1) { g.DrawArc(pen, center.X-6, center.Y-6, 12, 12, 35, 285); g.DrawLine(pen, center.X-7, center.Y-5, center.X-2, center.Y-6); }
                else { g.DrawEllipse(pen, center.X-7, center.Y-4, 14, 8); using (var dot = new SolidBrush(Enabled ? ForeColor : Color.Gray)) g.FillEllipse(dot, center.X-2, center.Y-2, 4, 4); }
            }
        }
    }

    private static Color Blend(Color a, Color b, float amount)
    {
        amount = Math.Max(0F, Math.Min(1F, amount));
        return Color.FromArgb((int)(a.A + (b.A-a.A)*amount), (int)(a.R+(b.R-a.R)*amount), (int)(a.G+(b.G-a.G)*amount), (int)(a.B+(b.B-a.B)*amount));
    }

    private static GraphicsPath RoundPath(Rectangle rectangle, int radius)
    {
        int diameter = radius * 2;
        var path = new GraphicsPath();
        path.AddArc(rectangle.Left, rectangle.Top, diameter, diameter, 180, 90);
        path.AddArc(rectangle.Right - diameter, rectangle.Top, diameter, diameter, 270, 90);
        path.AddArc(rectangle.Right - diameter, rectangle.Bottom - diameter, diameter, diameter, 0, 90);
        path.AddArc(rectangle.Left, rectangle.Bottom - diameter, diameter, diameter, 90, 90);
        path.CloseFigure();
        return path;
    }

    private sealed class ChineseNameComparer : IComparer<string>
    {
        private readonly CompareInfo compare = CultureInfo.GetCultureInfo("zh-CN").CompareInfo;
        public int Compare(string x, string y)
        {
            return compare.Compare(x ?? "", y ?? "", CompareOptions.IgnoreCase | CompareOptions.IgnoreSymbols | CompareOptions.StringSort);
        }
    }

    private sealed class DesktopFolderView
    {
        private readonly INativeFolderView view;

        private DesktopFolderView(INativeFolderView view)
        {
            this.view = view;
        }

        public static DesktopFolderView Open()
        {
            object shellWindows = null;
            object desktopDispatch = null;
            try
            {
                Type shellWindowsType = Type.GetTypeFromCLSID(new Guid("9BA05972-F6A8-11CF-A442-00A0C90A8F39"));
                shellWindows = Activator.CreateInstance(shellWindowsType);
                object[] arguments = { 0, null, 8, 0, 1 }; // CSIDL_DESKTOP, SWC_DESKTOP, SWFO_NEEDDISPATCH
                desktopDispatch = shellWindows.GetType().InvokeMember(
                    "FindWindowSW", BindingFlags.InvokeMethod, null, shellWindows, arguments, CultureInfo.InvariantCulture);
                if (desktopDispatch == null) throw new InvalidOperationException("无法连接 Windows 桌面视图。");

                var provider = (INativeServiceProvider)desktopDispatch;
                Guid topLevelBrowser = new Guid("4C96BE40-915C-11CF-99D3-00AA004AE837");
                Guid shellBrowserId = typeof(INativeShellBrowser).GUID;
                IntPtr browserPointer;
                ThrowIfFailed(provider.QueryService(ref topLevelBrowser, ref shellBrowserId, out browserPointer), "无法获取桌面浏览器。");

                INativeShellBrowser browser;
                try { browser = (INativeShellBrowser)Marshal.GetTypedObjectForIUnknown(browserPointer, typeof(INativeShellBrowser)); }
                finally { Marshal.Release(browserPointer); }

                IntPtr shellViewPointer;
                ThrowIfFailed(browser.QueryActiveShellView(out shellViewPointer), "无法获取活动桌面视图。");
                try
                {
                    Guid folderViewId = typeof(INativeFolderView).GUID;
                    IntPtr folderViewPointer;
                    ThrowIfFailed(Marshal.QueryInterface(shellViewPointer, ref folderViewId, out folderViewPointer), "桌面视图不支持图标定位。");
                    try
                    {
                        var folderView = (INativeFolderView)Marshal.GetTypedObjectForIUnknown(folderViewPointer, typeof(INativeFolderView));
                        return new DesktopFolderView(folderView);
                    }
                    finally { Marshal.Release(folderViewPointer); }
                }
                finally { Marshal.Release(shellViewPointer); }
            }
            finally
            {
                if (desktopDispatch != null && Marshal.IsComObject(desktopDispatch)) Marshal.FinalReleaseComObject(desktopDispatch);
                if (shellWindows != null && Marshal.IsComObject(shellWindows)) Marshal.FinalReleaseComObject(shellWindows);
            }
        }

        public IntPtr GetItemPidl(int index)
        {
            IntPtr pidl;
            ThrowIfFailed(view.Item(index, out pidl), "无法定位第 " + (index + 1) + " 个桌面图标。");
            if (pidl == IntPtr.Zero) throw new InvalidOperationException("桌面图标标识为空。");
            return pidl;
        }

        public int GetItemCount()
        {
            int count;
            ThrowIfFailed(view.ItemCount(2, out count), "无法读取桌面图标数量。"); // SVGIO_ALLVIEW
            return count;
        }

        public ShellPoint GetSpacing()
        {
            var spacing = new ShellPoint();
            ThrowIfFailed(view.GetSpacing(ref spacing), "无法读取桌面图标间距。");
            return spacing;
        }

        public bool TryGetItemPosition(int index, out ShellPoint point)
        {
            point = new ShellPoint();
            IntPtr pidl = IntPtr.Zero;
            try
            {
                if (view.Item(index, out pidl) < 0 || pidl == IntPtr.Zero) return false;
                return view.GetItemPosition(pidl, out point) >= 0;
            }
            finally { if (pidl != IntPtr.Zero) Marshal.FreeCoTaskMem(pidl); }
        }

        public bool TryGetItemPosition(IntPtr pidl, out ShellPoint point)
        {
            return view.GetItemPosition(pidl, out point) >= 0;
        }

        public void SelectAndPositionItems(IntPtr[] pidls, ShellPoint[] points, uint flags)
        {
            if (pidls.Length != points.Length) throw new ArgumentException("图标和坐标数量不一致。");
            int pointSize = Marshal.SizeOf(typeof(ShellPoint));
            IntPtr pidlArray = Marshal.AllocHGlobal(IntPtr.Size * pidls.Length);
            IntPtr pointArray = Marshal.AllocHGlobal(pointSize * points.Length);
            try
            {
                Marshal.Copy(pidls, 0, pidlArray, pidls.Length);
                for (int i = 0; i < points.Length; i++)
                    Marshal.StructureToPtr(points[i], IntPtr.Add(pointArray, i * pointSize), false);
                ThrowIfFailed(
                    view.SelectAndPositionItems((uint)pidls.Length, pidlArray, pointArray, flags),
                    "Windows 拒绝了桌面图标定位请求。");
            }
            finally
            {
                Marshal.FreeHGlobal(pointArray);
                Marshal.FreeHGlobal(pidlArray);
            }
        }

        private static void ThrowIfFailed(int hresult, string message)
        {
            if (hresult < 0) throw new InvalidOperationException(message + "（错误 0x" + hresult.ToString("X8") + "）");
        }
    }
}
