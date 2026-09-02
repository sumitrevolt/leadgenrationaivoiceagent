// Unity → browser boundary. Only two exports; both funnel into the shell's allowlisted
// LG_BRIDGE (frontend/office_blueprint.html). No other window access is permitted here.
mergeInto(LibraryManager.library, {
  LG_BridgeInvoke: function (payloadPtr) {
    try {
      var payload = UTF8ToString(payloadPtr);
      if (window.LG_BRIDGE && typeof window.LG_BRIDGE.invoke === "function") {
        window.LG_BRIDGE.invoke(payload);
      }
    } catch (e) { console.warn("HostBridge.jslib invoke failed", e); }
  },
  LG_SelectInHost: function (kindPtr, idPtr) {
    try {
      var kind = UTF8ToString(kindPtr), id = UTF8ToString(idPtr);
      if (window.LG_BRIDGE && typeof window.LG_BRIDGE.select === "function") {
        window.LG_BRIDGE.select(kind, id);
      }
    } catch (e) { console.warn("HostBridge.jslib select failed", e); }
  },
});
