"""Native IUIAutomation (COM) text checks of a ui4me text field, as Narrator reads it (Core 0.5 F0504).

    python uia_native_text.py OUT.json

Needs ``comtypes`` (test-only) and a running app with a window titled ``ui4me uia probe`` whose
edit is named ``Your name`` (``uia_probe.ps1`` starts one; any equivalent app works). Selects
the field's text from its second character through a text range, then reads the selection back:
its text and bounding boxes. Run inside an interactive desktop session. Automated; not a person.
"""
import json
import sys
import time

import comtypes.client

UIA = comtypes.client.GetModule("UIAutomationCore.dll")


def main() -> int:
    cases = {}
    details = {}
    uia = comtypes.client.CreateObject("{ff48dba4-60ef-4201-aa87-54103eef594e}", interface=UIA.IUIAutomation)
    win = None
    for _ in range(60):
        win = uia.GetRootElement().FindFirst(UIA.TreeScope_Children, uia.CreatePropertyCondition(UIA.UIA_NamePropertyId, "ui4me uia probe"))
        if win:
            break
        time.sleep(0.25)
    cond = uia.CreateAndCondition(uia.CreatePropertyCondition(UIA.UIA_NamePropertyId, "Your name"),
                                  uia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, UIA.UIA_EditControlTypeId))
    edit = win.FindFirst(UIA.TreeScope_Descendants, cond)
    tp = edit.GetCurrentPattern(UIA.UIA_TextPatternId).QueryInterface(UIA.IUIAutomationTextPattern)
    details["document"] = tp.DocumentRange.GetText(100)
    r = tp.DocumentRange.Clone()
    r.MoveEndpointByUnit(UIA.TextPatternRangeEndpoint_Start, UIA.TextUnit_Character, 1)
    details["range"] = r.GetText(100)
    r.Select()
    text = None
    boxes = []
    for _ in range(25):
        sel = tp.GetSelection()
        if sel.Length:
            s0 = sel.GetElement(0)
            text, boxes = s0.GetText(100), list(s0.GetBoundingRectangles())
            if text == details["range"]:
                break
        time.sleep(0.2)
    details["selection"] = text
    details["boxes"] = boxes
    cases["N01_selection_text"] = bool(details["range"]) and details["range"] == details["document"][1:] and text == details["range"]
    cases["N02_selection_bounds"] = len(boxes) >= 4 and boxes[2] > 0 and boxes[3] > 0
    status = "passed" if all(cases.values()) else "failed"
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        json.dump({"status": status, "cases": cases, "details": details}, f, indent=2, ensure_ascii=False)
    for k, v in cases.items():
        print("passed" if v else "failed", k)
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
