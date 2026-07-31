using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
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
        public int NameOccurrence;
        public bool IsWhitelisted;
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
    [DllImport("user32.dll", EntryPoint = "GetWindowLongPtr")]
    private static extern IntPtr GetWindowLongPtr64(IntPtr hWnd, int index);
    [DllImport("user32.dll", EntryPoint = "SetWindowLongPtr")]
    private static extern IntPtr SetWindowLongPtr64(IntPtr hWnd, int index, IntPtr value);
    [DllImport("user32.dll")]
    private static extern bool SetWindowPos(IntPtr hWnd, IntPtr insertAfter, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll")]
    private static extern int GetSystemMetrics(int index);
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

    [STAThread]
    private static void Main()
    {
        try
        {
            EnableRequiredSystemIcons();
            SHChangeNotify(0x08000000, 0, IntPtr.Zero, IntPtr.Zero);
            Thread.Sleep(700);
            IntPtr listView = FindDesktopListView();
            if (listView == IntPtr.Zero)
                throw new InvalidOperationException("没有找到桌面图标区域。请先显示桌面后再运行此程序。");

            SendMessage(listView, WM_KEYDOWN, (IntPtr)VK_F5, IntPtr.Zero);
            SendMessage(listView, WM_KEYUP, (IntPtr)VK_F5, IntPtr.Zero);
            Thread.Sleep(500);

            DesktopFolderView folderView = DesktopFolderView.Open();
            List<DesktopItem> items = ReadItems(listView, folderView);
            if (items.Count == 0)
                throw new InvalidOperationException("未读取到桌面图标。");

            int protectedCount = items.Count(x => x.IsWhitelisted);
            items = items.Where(x => !x.IsWhitelisted)
                         .OrderBy(x => x.Group)
                         .ThenBy(x => x.Priority)
                         .ThenBy(x => x.FileKind ?? "")
                         .ThenBy(x => x.Name, new ChineseNameComparer())
                         .ToList();
            var occurrences = new Dictionary<string, int>(StringComparer.CurrentCultureIgnoreCase);
            foreach (DesktopItem item in items)
            {
                int occurrence;
                occurrences.TryGetValue(item.Name, out occurrence);
                item.NameOccurrence = occurrence;
                occurrences[item.Name] = occurrence + 1;
            }

            DisableAutomaticArrange(listView);
            PositionItems(listView, folderView, items);

            MessageBox.Show(
                "整理完成。\n\n顺序：此电脑、回收站、控制面板 → 其他应用程序 → 实体文件夹 → 文件夹快捷方式 → 压缩文件 → 分类文件。\n每组按中文拼音/英文首字母排序；排列方向为从上到下、从左到右。\n右侧三分之一区域有 " + protectedCount + " 个图标已保留原位。",
                "一键整理桌面", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }
        catch (Exception ex)
        {
            MessageBox.Show("整理未完成：\n" + ex.Message, "一键整理桌面", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
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
        uint pid;
        GetWindowThreadProcessId(listView, out pid);
        IntPtr process = OpenProcess(PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE, false, pid);
        if (process == IntPtr.Zero) throw new InvalidOperationException("无法读取桌面图标。");

        try
        {
            int itemCount = SendMessage(listView, LVM_GETITEMCOUNT, IntPtr.Zero, IntPtr.Zero).ToInt32();
            int textBytes = 520 * sizeof(char);
            int itemBytes = Marshal.SizeOf(typeof(LVITEM));
            IntPtr remoteText = VirtualAllocEx(process, IntPtr.Zero, (UIntPtr)textBytes, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
            IntPtr remoteItem = VirtualAllocEx(process, IntPtr.Zero, (UIntPtr)itemBytes, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
            IntPtr remotePoint = VirtualAllocEx(process, IntPtr.Zero, (UIntPtr)Marshal.SizeOf(typeof(POINT)), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
            if (remoteText == IntPtr.Zero || remoteItem == IntPtr.Zero || remotePoint == IntPtr.Zero)
                throw new InvalidOperationException("无法为桌面图标读取分配内存。");
            try
            {
                var items = new List<DesktopItem>();
                var pathResolver = new DesktopPathResolver();
                RECT desktopArea;
                GetClientRect(listView, out desktopArea);
                int whitelistStart = ((desktopArea.Right - desktopArea.Left) * 2) / 3;
                for (int i = 0; i < itemCount; i++)
                {
                    LVITEM lv = new LVITEM { iSubItem = 0, pszText = remoteText, cchTextMax = 520 };
                    IntPtr local = Marshal.AllocHGlobal(itemBytes);
                    try
                    {
                        Marshal.StructureToPtr(lv, local, false);
                        byte[] raw = new byte[itemBytes];
                        Marshal.Copy(local, raw, 0, itemBytes);
                        IntPtr written;
                        if (!WriteProcessMemory(process, remoteItem, raw, raw.Length, out written)) continue;
                        SendMessage(listView, LVM_GETITEMTEXTW, (IntPtr)i, remoteItem);
                        byte[] text = new byte[textBytes];
                        IntPtr read;
                        if (!ReadProcessMemory(process, remoteText, text, text.Length, out read)) continue;
                        string name = Encoding.Unicode.GetString(text);
                        int terminator = name.IndexOf('\0');
                        if (terminator >= 0) name = name.Substring(0, terminator);
                        if (String.IsNullOrWhiteSpace(name)) continue;
                        IntPtr identity = ReadItemIdentity(listView, process, remoteItem, i, itemBytes);
                        string sourcePath = TryGetPathFromRemotePidl(process, identity) ?? pathResolver.Resolve(name);
                        DesktopItem item = Classify(i, name, identity, sourcePath);
                        POINT currentPosition;
                        ShellPoint shellPosition;
                        if (folderView.TryGetItemPosition(i, out shellPosition))
                            currentPosition = new POINT { X = shellPosition.X, Y = shellPosition.Y };
                        else
                            currentPosition = ReadItemPosition(listView, process, remotePoint, i);
                        // The three system icons stay fixed at the beginning even if moved accidentally.
                        item.IsWhitelisted = item.Priority >= 3 && currentPosition.X >= whitelistStart;
                        items.Add(item);
                    }
                    finally { Marshal.FreeHGlobal(local); }
                }
                return items;
            }
            finally
            {
                if (remoteText != IntPtr.Zero) VirtualFreeEx(process, remoteText, UIntPtr.Zero, MEM_RELEASE);
                if (remoteItem != IntPtr.Zero) VirtualFreeEx(process, remoteItem, UIntPtr.Zero, MEM_RELEASE);
                if (remotePoint != IntPtr.Zero) VirtualFreeEx(process, remotePoint, UIntPtr.Zero, MEM_RELEASE);
            }
        }
        finally { CloseHandle(process); }
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

    private static void DisableAutomaticArrange(IntPtr listView)
    {
        long style = GetWindowLongPtr64(listView, GWL_STYLE).ToInt64();
        long newStyle = style & ~(LVS_AUTOARRANGE | LVS_SORTASCENDING | LVS_SORTDESCENDING);
        SetWindowLongPtr64(listView, GWL_STYLE, new IntPtr(newStyle));
        SetWindowPos(listView, IntPtr.Zero, 0, 0, 0, 0, 0x0020 | 0x0001 | 0x0002 | 0x0004 | 0x0020);
    }

    private static void PositionItems(IntPtr listView, DesktopFolderView folderView, List<DesktopItem> items)
    {
        RECT area;
        if (!GetClientRect(listView, out area)) throw new InvalidOperationException("无法读取桌面可用区域。");
        int width = Math.Max(1, area.Right - area.Left);
        int safeWidth = Math.Max(1, (width * 2) / 3);
        int spacingX = Math.Max(85, GetSystemMetrics(SM_CXICONSPACING));
        int spacingY = Math.Max(90, GetSystemMetrics(SM_CYICONSPACING));
        int rows = Math.Max(1, (area.Bottom - area.Top - 20) / spacingY);
        int columns = Math.Max(1, (safeWidth - 20) / spacingX);
        if (items.Count >= rows * columns)
            throw new InvalidOperationException("左侧可整理区域至少需要保留一个空格，才能可靠地交换图标位置。请减少一个图标或缩小图标后重试。");
        var pidls = new IntPtr[items.Count];
        var points = new ShellPoint[items.Count];
        try
        {
            for (int position = 0; position < items.Count; position++)
            {
                int x = 10 + (position / rows) * spacingX;
                int y = 10 + (position % rows) * spacingY;
                pidls[position] = folderView.GetItemPidl(items[position].Index);
                points[position] = new ShellPoint { X = x, Y = y };
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
        finally
        {
            foreach (IntPtr pidl in pidls)
                if (pidl != IntPtr.Zero) Marshal.FreeCoTaskMem(pidl);
        }
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

        ShellPoint empty = FindEmptyGridPoint(actual, rows, columns, spacingX, spacingY);
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
        int spacingY)
    {
        for (int column = columns - 1; column >= 0; column--)
        {
            for (int row = rows - 1; row >= 0; row--)
            {
                var candidate = new ShellPoint { X = 10 + column * spacingX, Y = 10 + row * spacingY };
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
