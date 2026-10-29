document.addEventListener("DOMContentLoaded", function () {
    const search = document.getElementById("nav-search");
    const toggle = document.querySelector(".nav-search-toggle");
    const input = document.getElementById("nav-student-search");
    const panel = document.getElementById("nav-search-panel");
    const resultsBox = document.getElementById("nav-search-results");
    const liveRegion = document.getElementById("nav-search-live");

    function closeDropdowns() {
        document.querySelectorAll(".nav-dropdown.show").forEach(function (menu) {
            const button = menu.parentElement.querySelector("[data-bs-toggle='dropdown']");
            if (button && window.bootstrap) {
                window.bootstrap.Dropdown.getOrCreateInstance(button).hide();
            }
        });
    }

    if (!search || !input || !panel || !resultsBox) {
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") closeDropdowns();
        });
        return;
    }

    let students = [];
    let activeIndex = -1;
    let debounceTimer = null;
    let controller = null;
    let requestId = 0;

    function openPanel() {
        panel.classList.add("is-open");
        input.setAttribute("aria-expanded", "true");
    }

    function closeSearch(collapse) {
        panel.classList.remove("is-open");
        input.setAttribute("aria-expanded", "false");
        input.removeAttribute("aria-activedescendant");
        activeIndex = -1;
        if (collapse) {
            search.classList.remove("is-expanded");
            if (toggle) toggle.setAttribute("aria-expanded", "false");
        }
    }

    function expandSearch() {
        search.classList.add("is-expanded");
        if (toggle) toggle.setAttribute("aria-expanded", "true");
        input.focus();
    }

    function message(text, isError) {
        const item = document.createElement("p");
        item.className = isError ? "nav-search-error" : "nav-search-empty";
        item.textContent = text;
        resultsBox.replaceChildren(item);
    }

    function setActive(index) {
        if (!students.length) return;
        activeIndex = (index + students.length) % students.length;
        resultsBox.querySelectorAll("[role='option']").forEach(function (option, optionIndex) {
            const selected = optionIndex === activeIndex;
            option.classList.toggle("is-active", selected);
            option.setAttribute("aria-selected", selected ? "true" : "false");
            if (selected) {
                input.setAttribute("aria-activedescendant", option.id);
                option.scrollIntoView({ block: "nearest" });
            }
        });
    }

    function textElement(tag, className, text) {
        const element = document.createElement(tag);
        element.className = className;
        element.textContent = text;
        return element;
    }

    function renderResults(items) {
        students = items;
        activeIndex = -1;
        input.removeAttribute("aria-activedescendant");
        resultsBox.replaceChildren();
        liveRegion.textContent = items.length
            ? items.length + (items.length === 1 ? " student found" : " students found")
            : "No students found";

        if (!items.length) {
            message("No students found.", false);
            return;
        }

        items.forEach(function (student, index) {
            const row = document.createElement("div");
            row.className = "nav-search-result";
            row.id = "nav-student-option-" + index;
            row.setAttribute("role", "option");
            row.setAttribute("aria-selected", "false");

            const details = document.createElement("div");
            details.appendChild(textElement("strong", "nav-search-name", student.name));
            details.appendChild(textElement("span", "nav-search-number", student.student_number));

            const meta = document.createElement("div");
            meta.className = "nav-search-meta";
            let course = student.program || "Not enrolled";
            if (student.course_year) course += " · Course year " + student.course_year;
            meta.appendChild(textElement("span", "", course));
            const status = textElement(
                "span",
                "nav-search-status" + (student.status === "Deferred" ? " is-deferred" : ""),
                student.status
            );
            meta.appendChild(status);
            details.appendChild(meta);

            const actions = document.createElement("div");
            actions.className = "nav-search-actions";
            const open = textElement("a", "nav-search-action", "Open");
            open.href = student.detail_url;
            actions.appendChild(open);

            if (student.payment_url) {
                const pay = textElement("a", "nav-search-action nav-search-action--pay", "Pay");
                pay.href = student.payment_url;
                actions.appendChild(pay);
            } else {
                const pay = textElement("span", "nav-search-action", "Pay");
                pay.setAttribute("aria-disabled", "true");
                pay.title = "Payments are available for active students";
                actions.appendChild(pay);
            }

            row.appendChild(details);
            row.appendChild(actions);
            row.addEventListener("mousemove", function () {
                if (activeIndex !== index) setActive(index);
            });
            resultsBox.appendChild(row);
        });
    }

    async function runSearch(query) {
        if (controller) controller.abort();
        controller = new AbortController();
        const currentRequest = ++requestId;
        resultsBox.setAttribute("aria-busy", "true");
        message("Searching…", false);
        openPanel();

        try {
            const url = new URL(search.dataset.searchUrl, window.location.origin);
            url.searchParams.set("q", query);
            url.searchParams.set("include_deferred", "1");
            const response = await fetch(url.toString(), {
                signal: controller.signal,
                headers: { "X-Requested-With": "XMLHttpRequest" },
            });
            if (!response.ok) throw new Error("Search request failed");
            const data = await response.json();
            if (currentRequest !== requestId) return;
            renderResults(Array.isArray(data.students) ? data.students.slice(0, 8) : []);
        } catch (error) {
            if (error.name === "AbortError") return;
            if (currentRequest !== requestId) return;
            students = [];
            liveRegion.textContent = "Search unavailable";
            message("Search unavailable. Try again.", true);
        } finally {
            if (currentRequest === requestId) resultsBox.setAttribute("aria-busy", "false");
        }
    }

    input.addEventListener("input", function () {
        const query = input.value.trim();
        window.clearTimeout(debounceTimer);
        if (controller) controller.abort();
        requestId += 1;
        if (query.length < 2) {
            students = [];
            resultsBox.replaceChildren();
            liveRegion.textContent = "";
            closeSearch(false);
            return;
        }
        debounceTimer = window.setTimeout(function () {
            runSearch(query);
        }, 200);
    });

    input.addEventListener("keydown", function (event) {
        if (event.key === "ArrowDown" && students.length) {
            event.preventDefault();
            openPanel();
            setActive(activeIndex + 1);
        } else if (event.key === "ArrowUp" && students.length) {
            event.preventDefault();
            openPanel();
            setActive(activeIndex < 0 ? students.length - 1 : activeIndex - 1);
        } else if (event.key === "Enter" && students.length) {
            event.preventDefault();
            const selected = students[activeIndex < 0 ? 0 : activeIndex];
            window.location.assign(selected.detail_url);
        } else if (event.key === "Escape") {
            event.preventDefault();
            closeSearch(true);
        }
    });

    input.addEventListener("focus", function () {
        if (input.value.trim().length >= 2 && (students.length || resultsBox.childElementCount)) {
            openPanel();
        }
    });

    if (toggle) {
        toggle.setAttribute("aria-expanded", "false");
        toggle.setAttribute("aria-controls", "nav-search");
        toggle.addEventListener("click", expandSearch);
    }

    document.addEventListener("click", function (event) {
        if (!search.contains(event.target) && (!toggle || !toggle.contains(event.target))) {
            closeSearch(true);
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            closeSearch(true);
            closeDropdowns();
            return;
        }

        const target = event.target;
        const typing = target && (
            target.tagName === "INPUT" ||
            target.tagName === "TEXTAREA" ||
            target.tagName === "SELECT" ||
            target.isContentEditable
        );
        if (typing) return;

        const shortcut = event.key === "/" ||
            ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k");
        if (shortcut) {
            event.preventDefault();
            expandSearch();
        }
    });
});
