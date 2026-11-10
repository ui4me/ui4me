using System.Management.Automation;
using System.Management.Automation.Language;

namespace Ui4me.Managed;

internal static class ScriptClosure
{
    internal static ScriptBlock Capture(ScriptBlock source)
    {
        var captured = source.GetNewClosure();
        // GetNewClosure copies the current local scope, but omits variables
        // inherited from a dynamic module when callbacks register more work.
        // Merge only referenced missing names from the original module;
        // variables local to this registration retain precedence.
        var origin = source.Module?.SessionState.PSVariable;
        var target = captured.Module?.SessionState.PSVariable;
        if (origin is null || target is null) return captured;
        foreach (var node in source.Ast.FindAll(n => n is VariableExpressionAst, true))
        {
            var variable = (VariableExpressionAst)node;
            if (!variable.VariablePath.IsUnqualified) continue;
            var name = variable.VariablePath.UserPath;
            if (target.Get(name) is not null) continue;
            var original = origin.Get(name);
            if (original is not null) target.Set(name, original.Value);
        }
        return captured;
    }
}
