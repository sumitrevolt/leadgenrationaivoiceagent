// Canonical status + blueprint colors. 1:1 with docs/UNITY_BLUEPRINT_STYLE_GUIDE.md —
// these hexes come from existing project tokens (control_center.html / graph legend /
// office_map room strokes). NEVER invent new colors here.
using System.Collections.Generic;
using UnityEngine;

namespace LeadGen.Office
{
    public static class StatusPalette
    {
        public static readonly Color Bg        = Hex("#0a0a0c");
        public static readonly Color GridDot   = Hex("#1a1d26");
        public static readonly Color Panel     = Hex("#111113");
        public static readonly Color Border    = Hex("#1e2028");
        public static readonly Color Text      = Hex("#e2e8f0");
        public static readonly Color Muted     = Hex("#64748b");
        public static readonly Color Amber     = Hex("#f59e0b"); // selection/accent

        public static readonly Color Healthy    = Hex("#22c55e");
        public static readonly Color Processing = Hex("#3b82f6");
        public static readonly Color Waiting    = Hex("#eab308");
        public static readonly Color Retry      = Hex("#f97316");
        public static readonly Color Failed     = Hex("#ef4444");
        public static readonly Color Idle       = Hex("#64748b");
        public static readonly Color Ai         = Hex("#a855f7");

        // Room stroke colors — mirror of office_map.html OFFICE.ROOMS (drift-locked in docs).
        public static readonly Dictionary<string, Color> RoomStroke = new()
        {
            { "coordinator",          Hex("#8b5cf6") },
            { "lead_lab",             Hex("#0ea5e9") },
            { "sales_crm",            Hex("#f97316") },
            { "voice_team",           Hex("#3b82f6") },
            { "marketing_team",       Hex("#ec4899") },
            { "qa_audit",             Hex("#eab308") },
            { "platform_engineering", Hex("#10b981") },
            { "admin_finance",        Hex("#64748b") },
        };

        public static Color ForStatus(string status)
        {
            var s = (status ?? "").ToLowerInvariant();
            if (s.Contains("fail") || s.Contains("error") || s.Contains("critical")) return Failed;
            if (s.Contains("retry")) return Retry;
            if (s.Contains("wait") || s.Contains("block") || s.Contains("degrad") || s.Contains("review") || s.Contains("partial")) return Waiting;
            if (s.Contains("work") || s.Contains("process") || s.Contains("run")) return Processing;
            if (s.Contains("health") || s.Contains("ok") || s.Contains("done")) return Healthy;
            return Idle; // offline/inactive/unknown — never fake green
        }

        private static Color Hex(string h)
        {
            return ColorUtility.TryParseHtmlString(h, out var c) ? c : Color.magenta;
        }
    }
}
