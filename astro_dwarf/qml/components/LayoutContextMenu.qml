import QtQuick

HudMenu {
    id: layoutMenu
    objectName: "layoutResetMenu"
    LayoutResetMenuItem {}
    HudMenuSeparator {}
    HudMenuItem {
        text: "Panels"
        info: true
        enabled: false
        accessibleDescription: "Show or hide control-page panels"
    }
    PanelVisibilityMenuItem { panelId: "status"; panelLabel: "System Status" }
    PanelVisibilityMenuItem { panelId: "vitals"; panelLabel: "Vitals" }
    PanelVisibilityMenuItem { panelId: "target"; panelLabel: "Target" }
    PanelVisibilityMenuItem { panelId: "camera"; panelLabel: "Camera" }
    PanelVisibilityMenuItem { panelId: "preview"; panelLabel: "Live View" }
    PanelVisibilityMenuItem { panelId: "commands"; panelLabel: "Commands" }
    PanelVisibilityMenuItem { panelId: "motion"; panelLabel: "Motion" }
    PanelVisibilityMenuItem { panelId: "upcoming"; panelLabel: "Up Next" }
    PanelVisibilityMenuItem { panelId: "log"; panelLabel: "Live Log" }
}
