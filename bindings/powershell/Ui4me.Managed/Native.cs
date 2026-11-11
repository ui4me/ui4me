using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;

namespace Ui4me.Managed;

public sealed class Ui4meException : Exception
{
    public int Code { get; }
    public Ui4meException(int code, string message) : base(message) => Code = code;
}

public static class Native
{
    private static readonly object Gate = new();
    private static string? moduleRoot;
    private static string? libraryPath;
    private static IntPtr handle;
    private static Exception? initializationFailure;

    public static void Initialize(string root)
    {
        root = Path.GetFullPath(root);
        lock (Gate)
        {
            if (initializationFailure is not null)
                throw new InvalidOperationException("Native initialization previously failed. Start a fresh process.", initializationFailure);
            if (moduleRoot is not null)
            {
                if (!String.Equals(moduleRoot, root, OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal))
                    throw new InvalidOperationException("Ui4me is already loaded from another module directory. Start a fresh PowerShell process after an upgrade.");
                return;
            }
            if (RuntimeInformation.ProcessArchitecture != Architecture.X64)
                throw new PlatformNotSupportedException("ui4me supports x64 Windows and Linux only.");
            var rid = OperatingSystem.IsWindows() ? "win-x64" : OperatingSystem.IsLinux() ? "linux-x64" : throw new PlatformNotSupportedException();
            var filename = OperatingSystem.IsWindows() ? "ui4me_core.dll" : "libui4me_core.so";
            var overridePath = Environment.GetEnvironmentVariable("UI4ME_NATIVE_LIB");
            if (overridePath is not null && !Path.IsPathFullyQualified(overridePath))
                throw new InvalidOperationException("UI4ME_NATIVE_LIB must be an absolute file path.");
            var path = Path.GetFullPath(overridePath ?? Path.Combine(root, "runtimes", rid, "native", filename));
            if (!File.Exists(path)) throw new FileNotFoundException("Native runtime missing. Install a packaged Ui4me module or build the repository.", path);
            var loaded = NativeLibrary.Load(path);
            // One resolver per assembly; retain the library for process lifetime.
            NativeLibrary.SetDllImportResolver(typeof(Native).Assembly,
                (name, assembly, searchPath) => name == "ui4me_core" ? loaded : IntPtr.Zero);
            handle = loaded;
            try
            {
                if (AbiVersion() != 1) throw new Ui4meException(-1, "This binding requires native ABI 1.");
                using var identity = JsonDocument.Parse(Utf8(BuildInfo()));
                if (identity.RootElement.GetProperty("product").GetString() != "ui4me" || identity.RootElement.GetProperty("version").GetString() != BuildVersion.Value)
                    throw new Ui4meException(-1, $"Native product/version does not match this ui4me {BuildVersion.Value} binding.");
            }
            catch (Exception failure) { initializationFailure = failure; throw; }
            moduleRoot = root;
            libraryPath = path;
        }
    }

    public static string GetInfoJson()
    {
        if (moduleRoot is null) throw new InvalidOperationException("Import the Ui4me module first.");
        using var document = JsonDocument.Parse(Utf8(BuildInfo()));
        var result = JsonSerializer.Deserialize<Dictionary<string, object?>>(document.RootElement.GetRawText())!;
        result["abi"] = AbiVersion();
        result["binding_version"] = BuildVersion.Value;
        result["library_path"] = libraryPath;
        return JsonSerializer.Serialize(result);
    }

    internal static string Utf8(IntPtr value) => Marshal.PtrToStringUTF8(value) ?? "";
    internal static void Check(int code)
    {
        if (code == 0) return;
        var text = Utf8(LastError());
        try
        {
            using var error = JsonDocument.Parse(text);
            if (error.RootElement.TryGetProperty("message", out var message)) text = message.GetString() ?? text;
        }
        catch (JsonException) { }
        throw new Ui4meException(code, text);
    }
    internal static JsonElement Command(ulong session, object command)
    {
        var json = JsonSerializer.Serialize(command);
        if (System.Text.Encoding.UTF8.GetByteCount(json) > 2 * 1024 * 1024)
            throw new ArgumentException("Native command exceeds 2 MiB.");
        Check(SessionCommand(session, json, out var response));
        // Copy borrowed memory before another native call on this thread.
        using var parsed = JsonDocument.Parse(response == IntPtr.Zero ? "{}" : Utf8(response));
        return parsed.RootElement.Clone();
    }

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    internal delegate int Callback(ulong session, IntPtr json, IntPtr user);
    [DllImport("ui4me_core", EntryPoint="ui4me_abi_version", CallingConvention=CallingConvention.Cdecl)]
    internal static extern uint AbiVersion();
    [DllImport("ui4me_core", EntryPoint="ui4me_build_info", CallingConvention=CallingConvention.Cdecl)]
    private static extern IntPtr BuildInfo();
    [DllImport("ui4me_core", EntryPoint="ui4me_last_error", CallingConvention=CallingConvention.Cdecl)]
    private static extern IntPtr LastError();
    [DllImport("ui4me_core", EntryPoint="ui4me_session_create", CallingConvention=CallingConvention.Cdecl)]
    internal static extern int SessionCreate([MarshalAs(UnmanagedType.LPUTF8Str)] string config, Callback callback, IntPtr user, out ulong session);
    [DllImport("ui4me_core", EntryPoint="ui4me_session_command", CallingConvention=CallingConvention.Cdecl)]
    private static extern int SessionCommand(ulong session, [MarshalAs(UnmanagedType.LPUTF8Str)] string command, out IntPtr response);
    [DllImport("ui4me_core", EntryPoint="ui4me_session_run", CallingConvention=CallingConvention.Cdecl)]
    internal static extern int SessionRun(ulong session);
    [DllImport("ui4me_core", EntryPoint="ui4me_session_post", CallingConvention=CallingConvention.Cdecl)]
    internal static extern int SessionPost(ulong session, ulong token);
    [DllImport("ui4me_core", EntryPoint="ui4me_session_complete", CallingConvention=CallingConvention.Cdecl)]
    internal static extern int SessionComplete(ulong session, ulong token);
    [DllImport("ui4me_core", EntryPoint="ui4me_session_stop", CallingConvention=CallingConvention.Cdecl)]
    internal static extern int SessionStop(ulong session);
    [DllImport("ui4me_core", EntryPoint="ui4me_session_destroy", CallingConvention=CallingConvention.Cdecl)]
    internal static extern int SessionDestroy(ulong session);
}
