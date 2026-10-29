(() => {
    "use strict";

    const sidebar = document.getElementById("main-sidebar");
    if (!sidebar) return;

    const root = document.documentElement;
    const mobile = window.matchMedia("(max-width: 768px)");
    const railToggle = sidebar.querySelector(".sidebar-rail-toggle");
    const menuToggle = document.querySelector(".sidebar-menu-toggle");
    const nav = sidebar.querySelector(".sidebar-nav");
    const storageKey = sidebar.dataset.sidebarStorageKey;
    const read = (key) => {
        try { return window.localStorage.getItem(`${storageKey}:${key}`); }
        catch (_) { return null; }
    };
    const write = (key, value) => {
        try { window.localStorage.setItem(`${storageKey}:${key}`, String(value)); }
        catch (_) { /* Navigation still works with storage disabled. */ }
    };
    let collapsed = read("collapsed") === "true";
    const inRail = () => collapsed && !mobile.matches;
    const groups = Array.from(sidebar.querySelectorAll("[data-sidebar-group]")).map((element) => {
        const saved = read(`group:${element.dataset.sidebarGroup}`);
        // A current destination always wins over a previously closed section.
        const preferred = element.dataset.active === "true" ||
            (saved === null ? element.open : saved === "true");
        const group = { element, preferred, renderedOpen: element.open };
        element.addEventListener("toggle", () => {
            // Programmatic rail/viewport changes must not overwrite preferences.
            if (inRail() || element.open === group.renderedOpen) return;
            group.preferred = element.open;
            group.renderedOpen = element.open;
            write(`group:${element.dataset.sidebarGroup}`, element.open);
        });
        return group;
    });

    const tooltips = [];
    if (window.bootstrap && window.bootstrap.Tooltip) {
        sidebar.querySelectorAll("[data-sidebar-link]").forEach((link) => {
            const tooltip = new window.bootstrap.Tooltip(link, {
                container: "body",
                placement: "right",
                trigger: "hover focus",
                customClass: "sidebar-tooltip",
                animation: !window.matchMedia("(prefers-reduced-motion: reduce)").matches,
            });
            tooltip.disable();
            tooltips.push(tooltip);
        });
    }

    function revealCurrent() {
        const current = nav.querySelector('[aria-current="page"]');
        if (!current) return;
        const bounds = nav.getBoundingClientRect();
        const item = current.getBoundingClientRect();
        if (item.bottom > bounds.bottom) nav.scrollTop += item.bottom - bounds.bottom + 8;
        else if (item.top < bounds.top) nav.scrollTop -= bounds.top - item.top + 8;
    }

    function applyLayout() {
        root.classList.toggle("sidebar-collapsed", collapsed);
        const rail = inRail();
        groups.forEach((group) => {
            group.renderedOpen = rail || group.preferred;
            group.element.open = group.renderedOpen;
        });
        const label = rail ? "Expand navigation" : "Collapse navigation";
        railToggle.setAttribute("aria-expanded", String(!rail));
        railToggle.setAttribute("aria-label", label);
        railToggle.setAttribute("title", label);
        railToggle.querySelector(".sidebar-label").textContent = label;
        tooltips.forEach((tooltip) => {
            tooltip.hide();
            if (rail) tooltip.enable();
            else tooltip.disable();
        });
        if (!mobile.matches) revealCurrent();
    }

    railToggle.addEventListener("click", () => {
        collapsed = !collapsed;
        write("collapsed", collapsed);
        applyLayout();
    });

    // Bootstrap owns the drawer's backdrop, focus trap, Escape, and return focus.
    sidebar.addEventListener("show.bs.offcanvas", (event) => {
        if (!mobile.matches) {
            event.preventDefault();
            return;
        }
        menuToggle.setAttribute("aria-expanded", "true");
    });
    sidebar.addEventListener("shown.bs.offcanvas", revealCurrent);
    sidebar.addEventListener("hidden.bs.offcanvas", () => {
        menuToggle.setAttribute("aria-expanded", "false");
        if (!mobile.matches && sidebar.contains(document.activeElement)) {
            const current = nav.querySelector('[aria-current="page"]') || nav.querySelector("a");
            current.focus({ preventScroll: true });
        }
    });
    mobile.addEventListener("change", () => {
        if (!mobile.matches && window.bootstrap && window.bootstrap.Offcanvas) {
            const drawer = window.bootstrap.Offcanvas.getInstance(sidebar);
            if (drawer) drawer.hide();
        }
        applyLayout();
    });
    applyLayout();
})();
