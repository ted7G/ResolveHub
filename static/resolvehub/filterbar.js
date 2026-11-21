// Turns the changelist's filter sidebar into a row of dropdown buttons above
// the table, so the table gets the page's full width. Each button shows the
// value in use ("Status: Open"). The links inside are Django's own, so
// filtering works exactly as before; without this script the sidebar stays.
"use strict";
{
    function capitalise(text) {
        return text.charAt(0).toUpperCase() + text.slice(1);
    }

    function build() {
        const changelist = document.getElementById("changelist");
        const panel = document.getElementById("changelist-filter");
        if (!changelist || !panel) {
            return;
        }
        const groups = [...panel.querySelectorAll("details[data-filter-title]")];

        groups.forEach((group) => {
            const summary = group.querySelector("summary");
            const title = capitalise(group.dataset.filterTitle);
            const items = [...group.querySelectorAll("li")];
            const selected = group.querySelector("li.selected");

            summary.textContent = title;
            if (selected && selected !== items[0]) {
                const value = document.createElement("span");
                value.className = "rh-filter-value";
                value.textContent = selected.textContent.trim();
                summary.append(": ", value);
                group.classList.add("is-active");
            }

            // Everything after the summary goes into the dropdown panel.
            const pop = document.createElement("div");
            pop.className = "rh-filter-pop";
            [...group.children].filter((child) => child !== summary).forEach((child) => pop.append(child));
            group.append(pop);
            group.open = false;

            group.addEventListener("toggle", () => {
                if (group.open) {
                    groups.forEach((other) => {
                        if (other !== group) {
                            other.open = false;
                        }
                    });
                    // Open towards the left when there isn't room on the right.
                    pop.classList.remove("is-flipped");
                    if (pop.getBoundingClientRect().right > document.documentElement.clientWidth - 8) {
                        pop.classList.add("is-flipped");
                    }
                    const search = pop.querySelector(".rh-filter-search");
                    if (search) {
                        search.focus();
                    }
                }
            });
        });

        changelist.classList.add("rh-has-filterbar");

        // Django's "✖ Clear all filters" link, shortened to fit the row.
        panel.querySelectorAll("#changelist-filter-extra-actions a").forEach((link) => {
            if (link.textContent.includes("Clear all filters")) {
                link.textContent = "Clear filters";
                link.classList.add("rh-clear-filters");
            }
        });

        // One toolbar row: the filter buttons on the left, search on the right.
        const toolbar = document.getElementById("toolbar");
        if (toolbar) {
            toolbar.prepend(panel);
        }

        document.addEventListener("click", (event) => {
            groups.forEach((group) => {
                if (group.open && !group.contains(event.target)) {
                    group.open = false;
                }
            });
        });
        document.addEventListener("keydown", (event) => {
            if (event.key !== "Escape") {
                return;
            }
            groups.forEach((group) => {
                if (group.open) {
                    group.open = false;
                    group.querySelector("summary").focus();
                }
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", build);
    } else {
        build();
    }
}
